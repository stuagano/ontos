"""
LLM Search Manager

Orchestrates conversational LLM search with tool-calling capabilities.
Uses Claude Sonnet 4.5 via Databricks serving endpoints to answer
business questions about data products, glossary terms, costs, and analytics.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from src.common.config import Settings, get_settings
from src.common.logging import get_logger
from src.common.sql_validator import SQLValidator, validate_and_prepare_query
from src.models.llm_search import (
    ConversationSession, ChatMessage, ChatResponse, MessageRole,
    ToolCall, ToolName, SessionSummary, LLMSearchStatus,
    SearchDataProductsParams, SearchGlossaryTermsParams,
    GetDataProductCostsParams, GetTableSchemaParams, ExecuteAnalyticsQueryParams
)

logger = get_logger(__name__)


# ============================================================================
# System Prompt
# ============================================================================

SYSTEM_PROMPT = """You are Ontos, an intelligent data governance assistant. You help users discover, understand, and analyze data within their organization.

## Your Capabilities

You have access to the following tools:

1. **search_data_products** - Search for data products by name, domain, description, or keywords. Use this to find available datasets.

2. **search_glossary_terms** - Search the knowledge graph for business concepts, terms, and their definitions from loaded ontologies and taxonomies.

3. **get_data_product_costs** - Get cost information for data products, including infrastructure, HR, storage, and other costs.

4. **get_table_schema** - Get the schema (columns and types) of a specific table. Use this before writing analytics queries.

5. **execute_analytics_query** - Execute a read-only SQL SELECT query against Databricks tables. Use this for aggregations, joins, and data analysis.

6. **explore_catalog_schema** - List all tables and views in a Unity Catalog schema with their columns. Use this to understand what data assets exist and suggest semantic models or data products.

7. **create_draft_data_contract** - Create a new draft data contract from schema information. Always create contracts in draft status for user review.

8. **create_draft_data_product** - Create a new draft data product, optionally linked to a contract. Always create products in draft status for user review.

9. **update_data_product** - Update an existing data product's domain, description, or status.

10. **update_data_contract** - Update an existing data contract's domain, description, or status.

11. **add_semantic_link** - Link a data product or contract to a business term/concept from the knowledge graph. Use search_glossary_terms first to find the concept IRI.

12. **list_semantic_links** - List semantic links (business term associations) for a data product or contract.

13. **remove_semantic_link** - Remove a semantic link. Use list_semantic_links first to find the link ID.

## Guidelines

- Always search for relevant data products or glossary terms before attempting analytics queries
- When executing analytics queries, first get the table schema to understand available columns
- Use explore_catalog_schema to discover tables in a database before suggesting semantic models
- Explain your reasoning and cite the data sources you used
- If you don't have access to certain data or a query fails, explain why and suggest alternatives
- Format responses with clear sections, tables, and bullet points for readability
- Be concise but thorough - include relevant context without unnecessary verbosity

## Response Format

When presenting data:
- Use markdown tables for tabular results. IMPORTANT: Tables must have proper line breaks between each row:
  ```
  | Column1 | Column2 |
  |---------|---------|
  | value1  | value2  |
  | value3  | value4  |
  ```
  Never put multiple table rows on a single line.
- Use bullet points for lists
- Bold important numbers and findings
- Include units (USD, %, etc.) where applicable

## Limitations

- You can only execute read-only SELECT queries
- Query results are limited to 1000 rows
- You can only access tables the user has permissions for
- Cost data may not be complete for all products
"""


# ============================================================================
# Tool Definitions for OpenAI API
# ============================================================================

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_data_products",
            "description": "Search for data products by name, domain, description, or keywords. Returns matching data products with their metadata.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for data products (e.g., 'customer', 'sales transactions')"
                    },
                    "domain": {
                        "type": "string",
                        "description": "Optional filter by domain (e.g., 'Customer', 'Sales', 'Finance')"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["active", "draft", "deprecated", "retired"],
                        "description": "Optional filter by product status"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_glossary_terms",
            "description": "Search the knowledge graph for business concepts, terms, and definitions from ontologies and taxonomies.",
            "parameters": {
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": "Business term or concept to search for (e.g., 'Customer', 'Sales', 'Transaction', 'Revenue')"
                    },
                    "domain": {
                        "type": "string",
                        "description": "Optional taxonomy/domain filter"
                    }
                },
                "required": ["term"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_data_product_costs",
            "description": "Get cost information for data products including infrastructure, HR, storage costs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "Specific product ID, or omit for all products"
                    },
                    "aggregate": {
                        "type": "boolean",
                        "description": "If true, return totals; if false, return per-product breakdown",
                        "default": False
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_schema",
            "description": "Get the schema (columns and data types) of a table from a data product.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_fqn": {
                        "type": "string",
                        "description": "Fully qualified table name (catalog.schema.table)"
                    }
                },
                "required": ["table_fqn"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_analytics_query",
            "description": "Execute a read-only SQL SELECT query against Databricks tables. Use for aggregations, joins, filtering.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "The SQL SELECT query to execute"
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Brief explanation of what this query does and why"
                    }
                },
                "required": ["sql", "explanation"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "explore_catalog_schema",
            "description": "List all tables and views in a Unity Catalog schema, including their columns and types. Use this to understand what data assets exist in a database/schema and suggest semantic models or data products.",
            "parameters": {
                "type": "object",
                "properties": {
                    "catalog": {
                        "type": "string",
                        "description": "Catalog name (e.g., 'demo_cat', 'main')"
                    },
                    "schema": {
                        "type": "string",
                        "description": "Schema/database name (e.g., 'demo_db', 'default')"
                    },
                    "include_columns": {
                        "type": "boolean",
                        "description": "If true, include column details for each table (default: true)"
                    }
                },
                "required": ["catalog", "schema"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_draft_data_contract",
            "description": "Create a new draft data contract based on schema information. The contract will be created in 'draft' status for user review. Use after exploring a catalog schema to formalize a data asset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name for the contract (e.g., 'Customer Master Data Contract')"
                    },
                    "description": {
                        "type": "string",
                        "description": "Business description of what this contract governs"
                    },
                    "domain": {
                        "type": "string",
                        "description": "Business domain (e.g., 'Customer', 'Sales', 'Finance')"
                    },
                    "tables": {
                        "type": "array",
                        "description": "List of tables to include in the contract schema",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Table name"},
                                "full_name": {"type": "string", "description": "Fully qualified table name (catalog.schema.table)"},
                                "description": {"type": "string", "description": "Table description"},
                                "columns": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "type": {"type": "string"},
                                            "description": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "required": ["name", "description", "domain"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_draft_data_product",
            "description": "Create a new draft data product. The product will be created in 'draft' status for user review. Optionally link to an existing data contract.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name for the data product (e.g., 'Customer Analytics Product')"
                    },
                    "description": {
                        "type": "string",
                        "description": "Business description and purpose of the data product"
                    },
                    "domain": {
                        "type": "string",
                        "description": "Business domain (e.g., 'Customer', 'Sales', 'Finance')"
                    },
                    "contract_id": {
                        "type": "string",
                        "description": "Optional: ID of an existing data contract to link to this product"
                    },
                    "output_tables": {
                        "type": "array",
                        "description": "List of output table FQNs this product provides",
                        "items": {"type": "string"}
                    }
                },
                "required": ["name", "description", "domain"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_data_product",
            "description": "Update an existing data product's properties like domain, description, or status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "ID of the data product to update"
                    },
                    "domain": {
                        "type": "string",
                        "description": "New business domain"
                    },
                    "description": {
                        "type": "string",
                        "description": "New business description/purpose"
                    },
                    "status": {
                        "type": "string",
                        "description": "New status (draft, active, deprecated)",
                        "enum": ["draft", "active", "deprecated"]
                    }
                },
                "required": ["product_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_data_contract",
            "description": "Update an existing data contract's properties like domain, description, or status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contract_id": {
                        "type": "string",
                        "description": "ID of the data contract to update"
                    },
                    "domain": {
                        "type": "string",
                        "description": "New business domain"
                    },
                    "description": {
                        "type": "string",
                        "description": "New business description/purpose"
                    },
                    "status": {
                        "type": "string",
                        "description": "New status (draft, active, deprecated)",
                        "enum": ["draft", "active", "deprecated"]
                    }
                },
                "required": ["contract_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_semantic_link",
            "description": "Link a data product or contract to a business term/concept from the knowledge graph. Use search_glossary_terms first to find the concept IRI.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "description": "Type of entity to link",
                        "enum": ["data_product", "data_contract"]
                    },
                    "entity_id": {
                        "type": "string",
                        "description": "ID of the entity to link"
                    },
                    "concept_iri": {
                        "type": "string",
                        "description": "IRI of the concept from the knowledge graph (from search_glossary_terms results)"
                    },
                    "concept_label": {
                        "type": "string",
                        "description": "Human-readable label for the concept"
                    },
                    "relationship_type": {
                        "type": "string",
                        "description": "Type of relationship (e.g., 'relatedTo', 'hasDomain', 'hasBusinessTerm')",
                        "default": "relatedTo"
                    }
                },
                "required": ["entity_type", "entity_id", "concept_iri", "concept_label"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_semantic_links",
            "description": "List semantic links (business term associations) for a data product or contract.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "description": "Type of entity",
                        "enum": ["data_product", "data_contract"]
                    },
                    "entity_id": {
                        "type": "string",
                        "description": "ID of the entity"
                    }
                },
                "required": ["entity_type", "entity_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remove_semantic_link",
            "description": "Remove a semantic link from a data product or contract. Use list_semantic_links first to find the link ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "link_id": {
                        "type": "string",
                        "description": "ID of the semantic link to remove (from list_semantic_links)"
                    }
                },
                "required": ["link_id"]
            }
        }
    }
]


# ============================================================================
# Session Storage (In-Memory for now, can be extended to Redis/DB)
# ============================================================================

@dataclass
class SessionStore:
    """In-memory session storage with expiration."""
    sessions: Dict[str, ConversationSession] = field(default_factory=dict)
    max_sessions_per_user: int = 10
    session_ttl_hours: int = 24
    
    def get(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID."""
        session = self.sessions.get(session_id)
        if session:
            # Check expiration
            age_hours = (datetime.utcnow() - session.created_at).total_seconds() / 3600
            if age_hours > self.session_ttl_hours:
                del self.sessions[session_id]
                return None
        return session
    
    def create(self, user_id: str) -> ConversationSession:
        """Create a new session for a user."""
        # Clean up old sessions for this user
        user_sessions = [
            (sid, s) for sid, s in self.sessions.items()
            if s.user_id == user_id
        ]
        user_sessions.sort(key=lambda x: x[1].updated_at, reverse=True)
        
        # Remove oldest if over limit
        while len(user_sessions) >= self.max_sessions_per_user:
            old_sid, _ = user_sessions.pop()
            del self.sessions[old_sid]
        
        session = ConversationSession(user_id=user_id)
        self.sessions[session.id] = session
        return session
    
    def delete(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False
    
    def list_for_user(self, user_id: str) -> List[SessionSummary]:
        """List sessions for a user."""
        result = []
        for session in self.sessions.values():
            if session.user_id == user_id:
                result.append(SessionSummary(
                    id=session.id,
                    title=session.title,
                    message_count=len(session.messages),
                    created_at=session.created_at,
                    updated_at=session.updated_at
                ))
        result.sort(key=lambda x: x.updated_at, reverse=True)
        return result


# ============================================================================
# LLM Search Manager
# ============================================================================

class LLMSearchManager:
    """
    Orchestrates conversational LLM search with tool-calling.
    
    Architecture:
    1. User sends message
    2. LLM processes with available tools
    3. If LLM requests tool calls, execute them
    4. Feed results back to LLM
    5. Repeat until LLM provides final response
    """
    
    def __init__(
        self,
        db: Session,
        settings: Settings,
        data_products_manager: Optional[Any] = None,
        data_contracts_manager: Optional[Any] = None,
        semantic_models_manager: Optional[Any] = None,
        costs_manager: Optional[Any] = None,
        search_manager: Optional[Any] = None,
        workspace_client: Optional[Any] = None
    ):
        self._db = db
        self._settings = settings
        self._data_products_manager = data_products_manager
        self._data_contracts_manager = data_contracts_manager
        self._semantic_models_manager = semantic_models_manager
        self._costs_manager = costs_manager
        self._search_manager = search_manager
        self._ws_client = workspace_client
        self._session_store = SessionStore()
        self._sql_validator = SQLValidator(max_row_limit=1000)
        
        logger.info(f"LLMSearchManager initialized (ws_client={workspace_client is not None}, semantic_models_manager={semantic_models_manager is not None})")
    
    # ========================================================================
    # Public API
    # ========================================================================
    
    def get_status(self) -> LLMSearchStatus:
        """Get the status of LLM search functionality."""
        return LLMSearchStatus(
            enabled=self._settings.LLM_ENABLED,
            endpoint=self._settings.LLM_ENDPOINT,
            disclaimer=self._settings.LLM_DISCLAIMER_TEXT or (
                "This feature uses AI to analyze data assets. AI-generated content may contain errors. "
                "Review all suggestions carefully before taking action."
            )
        )
    
    def list_sessions(self, user_id: str) -> List[SessionSummary]:
        """List conversation sessions for a user."""
        return self._session_store.list_for_user(user_id)
    
    def delete_session(self, session_id: str, user_id: str) -> bool:
        """Delete a session if owned by user."""
        session = self._session_store.get(session_id)
        if session and session.user_id == user_id:
            return self._session_store.delete(session_id)
        return False
    
    def get_session(self, session_id: str, user_id: str) -> Optional[ConversationSession]:
        """Get a session by ID if owned by user."""
        session = self._session_store.get(session_id)
        if session and session.user_id == user_id:
            return session
        return None
    
    async def chat(
        self,
        user_message: str,
        user_id: str,
        session_id: Optional[str] = None
    ) -> ChatResponse:
        """
        Process a chat message and return the assistant's response.
        
        Note: The workspace client passed to this manager should already have
        user credentials (OBO) for proper access control and audit trail.
        
        Args:
            user_message: The user's message
            user_id: ID of the user
            session_id: Optional session ID to continue conversation
            
        Returns:
            ChatResponse with the assistant's message
        """
        # Check if LLM is enabled
        if not self._settings.LLM_ENABLED:
            logger.warning("LLM chat requested but LLM_ENABLED is False")
            return ChatResponse(
                session_id="",
                message=ChatMessage(
                    role=MessageRole.ASSISTANT,
                    content="LLM search is not enabled. Please contact your administrator."
                ),
                tool_calls_executed=0,
                sources=[]
            )
        
        # Get or create session
        if session_id:
            session = self._session_store.get(session_id)
            if not session or session.user_id != user_id:
                session = self._session_store.create(user_id)
        else:
            session = self._session_store.create(user_id)
        
        # Add user message
        session.add_user_message(user_message)
        
        # Process with LLM
        try:
            response_content, tool_calls_executed, sources = await self._process_with_llm(
                session
            )
            
            # Add assistant response
            assistant_msg = session.add_assistant_message(response_content)
            
            return ChatResponse(
                session_id=session.id,
                message=assistant_msg,
                tool_calls_executed=tool_calls_executed,
                sources=sources
            )
            
        except Exception as e:
            logger.error(f"Error processing chat: {e}", exc_info=True)
            error_msg = session.add_assistant_message(
                f"I apologize, but I encountered an error processing your request: {str(e)}"
            )
            return ChatResponse(
                session_id=session.id,
                message=error_msg,
                tool_calls_executed=0,
                sources=[]
            )
    
    # ========================================================================
    # LLM Processing
    # ========================================================================
    
    async def _process_with_llm(
        self,
        session: ConversationSession
    ) -> Tuple[str, int, List[Dict[str, Any]]]:
        """
        Process conversation with LLM, handling tool calls.
        
        Returns:
            Tuple of (response_content, tool_calls_count, sources)
        """
        client = self._get_openai_client()
        total_tool_calls = 0
        sources: List[Dict[str, Any]] = []
        max_iterations = 10  # Prevent infinite loops (increased for complex multi-tool queries)
        
        for iteration in range(max_iterations):
            # Build messages for LLM
            messages = session.get_messages_for_llm(SYSTEM_PROMPT)
            
            # Call LLM
            try:
                logger.debug(f"Calling LLM (iteration {iteration + 1}/{max_iterations})")
                response = client.chat.completions.create(
                    model=self._settings.LLM_ENDPOINT,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    max_tokens=4096
                )
                logger.debug(f"LLM response received successfully")
            except Exception as llm_error:
                logger.error(f"LLM API call failed: {llm_error}", exc_info=True)
                raise RuntimeError(f"Failed to connect to LLM endpoint: {llm_error}")
            
            assistant_message = response.choices[0].message
            
            # Check if LLM wants to call tools
            if assistant_message.tool_calls:
                # Add assistant message with tool calls to session
                tool_calls = [
                    ToolCall(
                        id=tc.id,
                        name=ToolName(tc.function.name),
                        arguments=json.loads(tc.function.arguments) if tc.function.arguments else {}
                    )
                    for tc in assistant_message.tool_calls
                ]
                session.add_assistant_message(None, tool_calls)
                
                # Execute each tool call
                for tc in assistant_message.tool_calls:
                    total_tool_calls += 1
                    tool_name = tc.function.name
                    tool_args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    
                    logger.info(f"Executing tool: {tool_name} with args: {tool_args}")
                    
                    try:
                        result = await self._execute_tool(tool_name, tool_args)
                        # Log the result summary
                        if "error" in result:
                            logger.warning(f"Tool {tool_name} returned error: {result.get('error')}")
                            sources.append({
                                "tool": tool_name,
                                "args": tool_args,
                                "success": False,
                                "error": result.get('error')
                            })
                        else:
                            result_summary = str(result)[:500] + "..." if len(str(result)) > 500 else str(result)
                            logger.info(f"Tool {tool_name} result: {result_summary}")
                            sources.append({
                                "tool": tool_name,
                                "args": tool_args,
                                "success": True
                            })
                    except Exception as e:
                        logger.error(f"Tool execution raised exception: {type(e).__name__}: {e}", exc_info=True)
                        result = {"error": f"{type(e).__name__}: {str(e)}"}
                        sources.append({
                            "tool": tool_name,
                            "args": tool_args,
                            "success": False,
                            "error": str(e)
                        })
                    
                    # Add tool result to session
                    session.add_tool_result(tc.id, result)
            else:
                # No tool calls - return the response
                return assistant_message.content or "", total_tool_calls, sources
        
        # Max iterations reached
        logger.warning(f"Max LLM iterations ({max_iterations}) reached after {total_tool_calls} tool calls")
        return f"I apologize, but I reached the maximum number of steps ({max_iterations}) while processing your request. I made {total_tool_calls} tool calls. Please try a simpler question or break it into smaller parts.", total_tool_calls, sources
    
    def _get_openai_client(self):
        """Get OpenAI client for Databricks LLM serving endpoint.
        
        Authentication priority:
        1. DATABRICKS_TOKEN from settings/.env (for local development)
        2. Databricks SDK default config (OBO token in Databricks Apps)
        
        Note: We check .env settings first so local development uses the configured
        workspace, not ~/.databrickscfg. In Databricks Apps, DATABRICKS_TOKEN is
        typically not set, so it falls through to SDK config (OBO).
        """
        try:
            from openai import OpenAI
            
            token = None
            
            # First try explicit token from settings/.env (local development)
            token = self._settings.DATABRICKS_TOKEN or os.environ.get('DATABRICKS_TOKEN')
            if token:
                logger.info("Using token from settings/environment (PAT)")
            
            # Fall back to Databricks SDK config (OBO in Apps, ~/.databrickscfg locally)
            if not token:
                try:
                    from databricks.sdk.core import Config
                    config = Config()
                    headers = config.authenticate()
                    if headers and 'Authorization' in headers:
                        auth_header = headers['Authorization']
                        if auth_header.startswith('Bearer '):
                            token = auth_header[7:]
                            logger.info("Using token from Databricks SDK (user credentials)")
                except Exception as sdk_err:
                    logger.debug(f"Could not get token from SDK config: {sdk_err}")
            
            if not token:
                raise RuntimeError("No authentication token available. Ensure the app has access to a serving endpoint or set DATABRICKS_TOKEN.")
            
            # Determine base URL
            base_url = self._settings.LLM_BASE_URL
            if not base_url and self._settings.DATABRICKS_HOST:
                host = self._settings.DATABRICKS_HOST.rstrip('/')
                # Ensure the URL has a protocol
                if not host.startswith('http://') and not host.startswith('https://'):
                    host = f"https://{host}"
                base_url = f"{host}/serving-endpoints"
            
            if not base_url:
                raise RuntimeError("LLM_BASE_URL not configured. Set LLM_BASE_URL or DATABRICKS_HOST.")
            
            logger.info(f"Creating OpenAI client for base_url={base_url}, endpoint={self._settings.LLM_ENDPOINT}")
            return OpenAI(api_key=token, base_url=base_url)
            
        except Exception as e:
            logger.error(f"Failed to create OpenAI client: {e}", exc_info=True)
            raise RuntimeError(f"LLM connection failed: {e}")
    
    # ========================================================================
    # Tool Execution
    # ========================================================================
    
    async def _execute_tool(
        self,
        tool_name: str,
        args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a tool and return results.
        
        Note: Tools that access Unity Catalog use self._ws_client which should
        be configured with OBO credentials for proper access control.
        """
        
        if tool_name == "search_data_products":
            return await self._tool_search_data_products(**args)
        
        elif tool_name == "search_glossary_terms":
            return await self._tool_search_glossary_terms(**args)
        
        elif tool_name == "get_data_product_costs":
            return await self._tool_get_data_product_costs(**args)
        
        elif tool_name == "get_table_schema":
            return await self._tool_get_table_schema(**args)
        
        elif tool_name == "execute_analytics_query":
            return await self._tool_execute_analytics_query(**args)
        
        elif tool_name == "explore_catalog_schema":
            return await self._tool_explore_catalog_schema(**args)
        
        elif tool_name == "create_draft_data_contract":
            return await self._tool_create_draft_data_contract(**args)
        
        elif tool_name == "create_draft_data_product":
            return await self._tool_create_draft_data_product(**args)
        
        elif tool_name == "update_data_product":
            return await self._tool_update_data_product(**args)
        
        elif tool_name == "update_data_contract":
            return await self._tool_update_data_contract(**args)
        
        elif tool_name == "add_semantic_link":
            return await self._tool_add_semantic_link(**args)
        
        elif tool_name == "list_semantic_links":
            return await self._tool_list_semantic_links(**args)
        
        elif tool_name == "remove_semantic_link":
            return await self._tool_remove_semantic_link(**args)
        
        else:
            raise ValueError(f"Unknown tool: {tool_name}")
    
    async def _tool_search_data_products(
        self,
        query: str,
        domain: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for data products."""
        logger.info(f"[search_data_products] Starting - query='{query}', domain={domain}, status={status}")
        
        try:
            # Query database directly using our session
            from src.db_models.data_products import DataProductDb
            
            products_db = self._db.query(DataProductDb).limit(500).all()
            logger.debug(f"[search_data_products] Found {len(products_db)} total products in database")
            
            if not products_db:
                logger.info(f"[search_data_products] No products found in database")
                return {"products": [], "total_found": 0, "message": "No data products found"}
            
            # Filter by query (name, description, domain)
            query_lower = query.lower() if query and query != '*' else ''
            filtered = []
            
            for p in products_db:
                # If query is empty or '*', include all products
                if not query_lower:
                    include = True
                else:
                    # Match on name
                    name_match = query_lower in (p.name or "").lower()
                    
                    # Match on description (stored as JSON)
                    desc_match = False
                    if p.description:
                        import json
                        try:
                            desc_dict = json.loads(p.description) if isinstance(p.description, str) else p.description
                            if isinstance(desc_dict, dict):
                                desc_text = desc_dict.get('purpose', '')
                                desc_match = query_lower in desc_text.lower()
                        except:
                            pass
                    
                    # Match on domain
                    domain_match = query_lower in (p.domain or "").lower()
                    
                    include = name_match or desc_match or domain_match
                
                if include:
                    # Apply filters
                    if domain and p.domain and p.domain.lower() != domain.lower():
                        continue
                    if status and p.status != status:
                        continue
                    
                    # Extract output tables from output_ports JSON
                    output_tables = []
                    if p.output_ports:
                        import json
                        try:
                            ports = json.loads(p.output_ports) if isinstance(p.output_ports, str) else p.output_ports
                            if isinstance(ports, list):
                                for port in ports:
                                    if isinstance(port, dict):
                                        output_tables.append(port.get('name', 'Unknown'))
                        except:
                            pass
                    
                    # Extract description purpose from JSON
                    desc_purpose = None
                    if p.description:
                        try:
                            desc_dict = json.loads(p.description) if isinstance(p.description, str) else p.description
                            if isinstance(desc_dict, dict):
                                desc_purpose = desc_dict.get('purpose')
                        except:
                            pass
                    
                    filtered.append({
                        "id": str(p.id),
                        "name": p.name,
                        "domain": p.domain,
                        "description": desc_purpose,
                        "status": p.status,
                        "output_tables": output_tables[:5],  # Limit for response size
                        "version": p.version
                    })
            
            logger.info(f"[search_data_products] SUCCESS: Found {len(filtered)} matching products")
            return {
                "products": filtered[:20],  # Limit results
                "total_found": len(filtered)
            }
            
        except Exception as e:
            logger.error(f"[search_data_products] FAILED: {type(e).__name__}: {e}", exc_info=True)
            return {"error": f"{type(e).__name__}: {str(e)}", "products": []}
    
    async def _tool_search_glossary_terms(
        self,
        term: str,
        domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for business terms/concepts in the knowledge graph."""
        logger.info(f"[search_glossary_terms] Starting - term='{term}', domain={domain}")
        
        if not self._semantic_models_manager:
            logger.warning(f"[search_glossary_terms] FAILED: semantic_models_manager is None")
            return {"error": "Knowledge graph not available", "terms": []}
        
        try:
            # Search concepts in the semantic models / knowledge graph
            # Results are ConceptSearchResult with nested 'concept' (OntologyConcept)
            results = self._semantic_models_manager.search_ontology_concepts(term, limit=20)
            
            terms = []
            for result in results:
                # result.concept is OntologyConcept with: iri, label, comment, source_context, etc.
                concept = result.concept
                terms.append({
                    "iri": concept.iri,
                    "name": concept.label or concept.iri.split('#')[-1].split('/')[-1],
                    "definition": concept.comment,
                    "taxonomy": concept.source_context,
                    "relevance_score": result.relevance_score,
                    "match_type": result.match_type
                })
            
            logger.info(f"[search_glossary_terms] SUCCESS: Found {len(results)} matching terms")
            return {
                "terms": terms[:15],
                "total_found": len(results),
                "source": "knowledge_graph"
            }
            
        except Exception as e:
            logger.error(f"[search_glossary_terms] FAILED: {type(e).__name__}: {e}", exc_info=True)
            return {"error": f"{type(e).__name__}: {str(e)}", "terms": []}
    
    async def _tool_get_data_product_costs(
        self,
        product_id: Optional[str] = None,
        aggregate: bool = False
    ) -> Dict[str, Any]:
        """Get cost information for data products."""
        logger.info(f"[get_data_product_costs] Starting - product_id={product_id}, aggregate={aggregate}")
        
        try:
            from src.db_models.costs import CostItemDb
            
            query = self._db.query(CostItemDb).filter(CostItemDb.entity_type == "data_product")
            
            if product_id:
                query = query.filter(CostItemDb.entity_id == product_id)
            
            items = query.all()
            logger.debug(f"[get_data_product_costs] Found {len(items)} cost items in database")
            
            if not items:
                logger.info(f"[get_data_product_costs] No cost data found")
                return {"message": "No cost data found", "total_usd": 0}
            
            if aggregate:
                # Sum all costs
                total_cents = sum(item.amount_cents for item in items)
                by_center: Dict[str, float] = {}
                for item in items:
                    center = item.cost_center or "OTHER"
                    by_center[center] = by_center.get(center, 0) + item.amount_cents / 100
                
                logger.info(f"[get_data_product_costs] SUCCESS: Aggregated {len(items)} cost items, total=${total_cents/100:.2f}")
                return {
                    "total_usd": total_cents / 100,
                    "by_cost_center": by_center,
                    "currency": "USD",
                    "product_count": len(set(item.entity_id for item in items))
                }
            else:
                # Group by product
                by_product: Dict[str, Dict[str, Any]] = {}
                for item in items:
                    pid = item.entity_id
                    if pid not in by_product:
                        # Get product name if available
                        product_name = pid
                        if self._data_products_manager:
                            try:
                                product = self._data_products_manager.get(pid)
                                if product:
                                    product_name = product.name or pid
                            except Exception:
                                pass
                        
                        by_product[pid] = {
                            "product_id": pid,
                            "product_name": product_name,
                            "total_usd": 0,
                            "items": []
                        }
                    
                    by_product[pid]["total_usd"] += item.amount_cents / 100
                    by_product[pid]["items"].append({
                        "title": item.title,
                        "cost_center": item.cost_center,
                        "amount_usd": item.amount_cents / 100,
                        "description": item.description
                    })
                
                logger.info(f"[get_data_product_costs] SUCCESS: Found costs for {len(by_product)} products")
                return {
                    "products": list(by_product.values()),
                    "total_usd": sum(p["total_usd"] for p in by_product.values()),
                    "currency": "USD"
                }
                
        except Exception as e:
            logger.error(f"[get_data_product_costs] FAILED: {type(e).__name__}: {e}", exc_info=True)
            return {"error": f"{type(e).__name__}: {str(e)}"}
    
    async def _tool_get_table_schema(
        self,
        table_fqn: str
    ) -> Dict[str, Any]:
        """Get schema for a table. Uses OBO workspace client for access control."""
        logger.info(f"[get_table_schema] Starting for table: {table_fqn}")
        
        if not self._ws_client:
            logger.error(f"[get_table_schema] FAILED: Workspace client not available")
            return {"error": "Workspace client not available"}
        
        try:
            # Validate table name
            self._sql_validator.sanitize_identifier(table_fqn)
            logger.debug(f"[get_table_schema] Table name validated: {table_fqn}")
            
            # Get table info from Unity Catalog
            logger.debug(f"[get_table_schema] Calling ws_client.tables.get for {table_fqn}")
            table_info = self._ws_client.tables.get(full_name_arg=table_fqn)
            
            columns = []
            if table_info.columns:
                for col in table_info.columns:
                    columns.append({
                        "name": col.name,
                        "type": col.type_text,
                        "nullable": col.nullable,
                        "comment": col.comment
                    })
            
            logger.info(f"[get_table_schema] SUCCESS: Found {len(columns)} columns for {table_fqn}")
            return {
                "table_fqn": table_fqn,
                "columns": columns,
                "table_type": str(table_info.table_type) if table_info.table_type else None,
                "comment": table_info.comment
            }
            
        except Exception as e:
            logger.error(f"[get_table_schema] FAILED for {table_fqn}: {type(e).__name__}: {e}", exc_info=True)
            return {"error": f"{type(e).__name__}: {str(e)}", "table_fqn": table_fqn}
    
    async def _tool_execute_analytics_query(
        self,
        sql: str,
        explanation: str
    ) -> Dict[str, Any]:
        """Execute an analytics query. Uses OBO workspace client for access control."""
        logger.info(f"[execute_analytics_query] Starting - explanation: {explanation}")
        logger.debug(f"[execute_analytics_query] SQL: {sql[:500]}...")
        
        if not self._ws_client:
            logger.error(f"[execute_analytics_query] FAILED: Workspace client not available")
            return {"error": "Workspace client not available"}
        
        try:
            # Validate and prepare query
            is_valid, prepared_sql, error = validate_and_prepare_query(
                sql,
                allowed_tables=None,  # TODO: Check user permissions
                max_rows=1000
            )
            
            if not is_valid:
                logger.warning(f"[execute_analytics_query] Query validation failed: {error}")
                return {"error": f"Query validation failed: {error}"}
            
            logger.info(f"[execute_analytics_query] Executing validated query: {prepared_sql[:200]}...")
            
            # Execute query
            # Note: This uses statement execution API
            warehouse_id = self._settings.DATABRICKS_WAREHOUSE_ID
            
            result = self._ws_client.statement_execution.execute_statement(
                statement=prepared_sql,
                warehouse_id=warehouse_id,
                wait_timeout="30s"
            )
            
            # Check status
            if result.status and result.status.state:
                state = str(result.status.state)
                if "FAILED" in state or "CANCELED" in state:
                    error_msg = result.status.error.message if result.status.error else "Query failed"
                    return {"error": error_msg, "state": state}
            
            # Extract results
            columns = []
            if result.manifest and result.manifest.schema and result.manifest.schema.columns:
                columns = [col.name for col in result.manifest.schema.columns]
            
            rows = []
            if result.result and result.result.data_array:
                rows = result.result.data_array
            
            truncated = len(rows) >= 1000
            
            logger.info(f"[execute_analytics_query] SUCCESS: {len(rows)} rows returned, {len(columns)} columns")
            return {
                "columns": columns,
                "rows": rows[:100],  # Limit for response size
                "row_count": len(rows),
                "explanation": explanation,
                "truncated": truncated,
                "full_result_available": len(rows) > 100
            }
            
        except Exception as e:
            logger.error(f"[execute_analytics_query] FAILED: {type(e).__name__}: {e}", exc_info=True)
            return {"error": f"{type(e).__name__}: {str(e)}"}

    async def _tool_explore_catalog_schema(
        self,
        catalog: str,
        schema: str,
        include_columns: bool = True
    ) -> Dict[str, Any]:
        """Explore all tables and views in a Unity Catalog schema. Uses OBO workspace client for access control."""
        logger.info(f"[explore_catalog_schema] Starting for {catalog}.{schema} (include_columns={include_columns})")
        
        if not self._ws_client:
            logger.error(f"[explore_catalog_schema] FAILED: Workspace client not available")
            return {"error": "Workspace client not available"}
        
        try:
            logger.debug(f"[explore_catalog_schema] Calling ws_client.tables.list for {catalog}.{schema}")
            
            # List tables in the schema
            tables_iterator = self._ws_client.tables.list(
                catalog_name=catalog,
                schema_name=schema
            )
            tables_list = list(tables_iterator)
            
            if not tables_list:
                return {
                    "catalog": catalog,
                    "schema": schema,
                    "table_count": 0,
                    "tables": [],
                    "message": f"No tables found in {catalog}.{schema}"
                }
            
            tables = []
            for table in tables_list:
                table_info = {
                    "name": table.name,
                    "full_name": table.full_name,
                    "table_type": str(table.table_type).replace("TableType.", "") if table.table_type else None,
                    "comment": table.comment,
                }
                
                # Get detailed column info if requested
                if include_columns:
                    try:
                        # Get full table details including columns
                        table_details = self._ws_client.tables.get(full_name_arg=table.full_name)
                        if table_details.columns:
                            table_info["columns"] = [
                                {
                                    "name": col.name,
                                    "type": col.type_text,
                                    "comment": col.comment,
                                    "nullable": col.nullable
                                }
                                for col in table_details.columns
                            ]
                            table_info["column_count"] = len(table_details.columns)
                    except Exception as col_err:
                        logger.warning(f"Could not get columns for {table.full_name}: {col_err}")
                        table_info["columns"] = []
                        table_info["column_error"] = str(col_err)
                
                tables.append(table_info)
            
            logger.info(f"[explore_catalog_schema] SUCCESS: Found {len(tables)} tables/views in {catalog}.{schema}")
            return {
                "catalog": catalog,
                "schema": schema,
                "table_count": len(tables),
                "tables": tables,
                "message": f"Found {len(tables)} tables/views in {catalog}.{schema}"
            }
            
        except Exception as e:
            logger.error(f"[explore_catalog_schema] FAILED for {catalog}.{schema}: {type(e).__name__}: {e}", exc_info=True)
            return {"error": f"{type(e).__name__}: {str(e)}", "catalog": catalog, "schema": schema}

    async def _tool_create_draft_data_contract(
        self,
        name: str,
        description: str,
        domain: str,
        tables: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Create a draft data contract from schema information."""
        logger.info(f"[create_draft_data_contract] Starting - name='{name}', domain={domain}, tables={len(tables) if tables else 0}")
        
        if not self._data_contracts_manager:
            logger.error(f"[create_draft_data_contract] FAILED: Data contracts manager not available")
            return {"error": "Data contracts manager not available"}
        
        try:
            import uuid
            logger.debug(f"[create_draft_data_contract] Building contract data for '{name}'")
            
            # Build schema objects from tables
            schema_objects = []
            if tables:
                for table in tables:
                    properties = []
                    for col in table.get("columns", []):
                        properties.append({
                            "property": col.get("name"),
                            "logicalType": col.get("type", "string"),
                            "physicalType": col.get("type", "STRING"),
                            "businessName": col.get("name"),
                            "description": col.get("description", "")
                        })
                    
                    schema_objects.append({
                        "name": table.get("name"),
                        "physicalName": table.get("full_name") or table.get("name"),
                        "description": table.get("description", ""),
                        "properties": properties
                    })
            
            # Build contract data in ODCS format
            contract_data = {
                "apiVersion": "v3.0.2",
                "kind": "DataContract",
                "name": name,
                "version": "0.1.0",
                "status": "draft",
                "domain": domain,
                "description": {
                    "purpose": description
                },
                "schema": schema_objects
            }
            
            # Create the contract
            created = self._data_contracts_manager.create_contract_with_relations(
                db=self._db,
                contract_data=contract_data,
                current_user=None  # Will use system default
            )
            
            logger.info(f"[create_draft_data_contract] SUCCESS: Created contract id={created.id}, name={created.name}")
            return {
                "success": True,
                "contract_id": created.id,
                "name": created.name,
                "version": created.version,
                "status": created.status,
                "message": f"Draft contract '{name}' created successfully. Review and publish it in the Data Contracts UI.",
                "url": f"/data-contracts/{created.id}"
            }
            
        except Exception as e:
            logger.error(f"[create_draft_data_contract] FAILED: {type(e).__name__}: {e}", exc_info=True)
            return {"error": f"{type(e).__name__}: {str(e)}"}

    async def _tool_create_draft_data_product(
        self,
        name: str,
        description: str,
        domain: str,
        contract_id: Optional[str] = None,
        output_tables: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a draft data product."""
        logger.info(f"[create_draft_data_product] Starting - name='{name}', domain={domain}, contract_id={contract_id}, output_tables={len(output_tables) if output_tables else 0}")
        
        if not self._data_products_manager:
            logger.error(f"[create_draft_data_product] FAILED: Data products manager not available")
            return {"error": "Data products manager not available"}
        
        try:
            import uuid
            logger.info(f"Creating draft data product: {name}")
            
            # Build output ports from tables
            output_ports = []
            if output_tables:
                for i, table_fqn in enumerate(output_tables):
                    output_ports.append({
                        "name": f"output_{i + 1}",
                        "server": table_fqn,
                        "description": f"Output table: {table_fqn}"
                    })
            
            # If contract_id provided, link it
            if contract_id and output_ports:
                output_ports[0]["dataContractId"] = contract_id
            
            # Build product data in ODPS format
            product_data = {
                "apiVersion": "v1.0.0",
                "kind": "DataProduct",
                "id": str(uuid.uuid4()),
                "name": name,
                "version": "0.1.0",
                "status": "draft",
                "domain": domain,
                "description": {
                    "purpose": description
                },
                "outputPorts": output_ports
            }
            
            # Create the product
            created = self._data_products_manager.create_product(
                product_data=product_data,
                db=self._db
            )
            
            logger.info(f"[create_draft_data_product] SUCCESS: Created product id={created.id}, name={created.name}")
            return {
                "success": True,
                "product_id": created.id,
                "name": created.name,
                "version": created.version,
                "status": created.status,
                "message": f"Draft product '{name}' created successfully. Review and publish it in the Data Products UI.",
                "url": f"/data-products/{created.id}"
            }
            
        except Exception as e:
            logger.error(f"[create_draft_data_product] FAILED: {type(e).__name__}: {e}", exc_info=True)
            return {"error": f"{type(e).__name__}: {str(e)}"}

    async def _tool_update_data_product(
        self,
        product_id: str,
        domain: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update an existing data product."""
        logger.info(f"[update_data_product] Starting - product_id={product_id}, domain={domain}, status={status}")
        
        if not self._data_products_manager:
            logger.error(f"[update_data_product] FAILED: Data products manager not available")
            return {"error": "Data products manager not available"}
        
        try:
            # Build update data
            update_data: Dict[str, Any] = {}
            if domain is not None:
                update_data["domain"] = domain
            if description is not None:
                update_data["description"] = {"purpose": description}
            if status is not None:
                update_data["status"] = status
            
            if not update_data:
                return {"error": "No fields to update. Provide at least one of: domain, description, status"}
            
            # Update the product
            updated = self._data_products_manager.update_product(
                product_id=product_id,
                product_data_dict=update_data,
                db=self._db
            )
            
            if not updated:
                return {"error": f"Data product '{product_id}' not found"}
            
            logger.info(f"[update_data_product] SUCCESS: Updated product id={updated.id}")
            return {
                "success": True,
                "product_id": updated.id,
                "name": updated.name,
                "domain": updated.domain,
                "status": updated.status,
                "message": f"Product '{updated.name}' updated successfully.",
                "url": f"/data-products/{updated.id}"
            }
            
        except Exception as e:
            logger.error(f"[update_data_product] FAILED: {type(e).__name__}: {e}", exc_info=True)
            return {"error": f"{type(e).__name__}: {str(e)}"}

    async def _tool_update_data_contract(
        self,
        contract_id: str,
        domain: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update an existing data contract."""
        logger.info(f"[update_data_contract] Starting - contract_id={contract_id}, domain={domain}, status={status}")
        
        if not self._data_contracts_manager:
            logger.error(f"[update_data_contract] FAILED: Data contracts manager not available")
            return {"error": "Data contracts manager not available"}
        
        try:
            # Build update data
            update_data: Dict[str, Any] = {}
            if domain is not None:
                update_data["domain"] = domain
            if description is not None:
                update_data["description"] = {"purpose": description}
            if status is not None:
                update_data["status"] = status
            
            if not update_data:
                return {"error": "No fields to update. Provide at least one of: domain, description, status"}
            
            # Update the contract
            updated = self._data_contracts_manager.update_contract_with_relations(
                db=self._db,
                contract_id=contract_id,
                contract_data=update_data,
                current_user=None
            )
            
            if not updated:
                return {"error": f"Data contract '{contract_id}' not found"}
            
            logger.info(f"[update_data_contract] SUCCESS: Updated contract id={updated.id}")
            return {
                "success": True,
                "contract_id": updated.id,
                "name": updated.name,
                "domain": updated.domain,
                "status": updated.status,
                "message": f"Contract '{updated.name}' updated successfully.",
                "url": f"/data-contracts/{updated.id}"
            }
            
        except Exception as e:
            logger.error(f"[update_data_contract] FAILED: {type(e).__name__}: {e}", exc_info=True)
            return {"error": f"{type(e).__name__}: {str(e)}"}

    async def _tool_add_semantic_link(
        self,
        entity_type: str,
        entity_id: str,
        concept_iri: str,
        concept_label: str,
        relationship_type: str = "relatedTo"
    ) -> Dict[str, Any]:
        """Add a semantic link from an entity to a knowledge graph concept."""
        logger.info(f"[add_semantic_link] Starting - entity_type={entity_type}, entity_id={entity_id}, concept_iri={concept_iri}")
        
        try:
            from src.controller.semantic_links_manager import SemanticLinksManager
            from src.models.semantic_links import EntitySemanticLinkCreate
            
            # Create manager instance
            manager = SemanticLinksManager(
                db=self._db,
                semantic_models_manager=self._semantic_models_manager
            )
            
            # Check if link already exists
            existing_links = manager.list_for_entity(entity_id=entity_id, entity_type=entity_type)
            for link in existing_links:
                if link.iri == concept_iri:
                    return {
                        "success": True,
                        "message": f"Semantic link to '{concept_label}' already exists for this {entity_type}",
                        "link_id": link.id,
                        "already_linked": True
                    }
            
            # Create the link
            link_data = EntitySemanticLinkCreate(
                entity_type=entity_type,
                entity_id=entity_id,
                iri=concept_iri,
                label=concept_label,
                relationship_type=relationship_type
            )
            
            created = manager.add(link_data, created_by="llm-assistant")
            self._db.commit()
            
            logger.info(f"[add_semantic_link] SUCCESS: Linked {entity_type} {entity_id} to concept '{concept_label}'")
            return {
                "success": True,
                "message": f"Linked {entity_type} to business term '{concept_label}'",
                "link_id": created.id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "concept_iri": concept_iri,
                "concept_label": concept_label,
                "relationship_type": relationship_type
            }
            
        except Exception as e:
            logger.error(f"[add_semantic_link] FAILED: {type(e).__name__}: {e}", exc_info=True)
            self._db.rollback()
            return {"error": f"{type(e).__name__}: {str(e)}"}

    async def _tool_list_semantic_links(
        self,
        entity_type: str,
        entity_id: str
    ) -> Dict[str, Any]:
        """List semantic links for an entity."""
        logger.info(f"[list_semantic_links] Starting - entity_type={entity_type}, entity_id={entity_id}")
        
        try:
            from src.controller.semantic_links_manager import SemanticLinksManager
            
            # Create manager instance
            manager = SemanticLinksManager(
                db=self._db,
                semantic_models_manager=self._semantic_models_manager
            )
            
            links = manager.list_for_entity(entity_id=entity_id, entity_type=entity_type)
            
            link_list = []
            for link in links:
                link_list.append({
                    "id": link.id,
                    "iri": link.iri,
                    "label": link.label,
                    "relationship_type": link.relationship_type,
                    "created_at": link.created_at.isoformat() if link.created_at else None
                })
            
            logger.info(f"[list_semantic_links] SUCCESS: Found {len(link_list)} links for {entity_type} {entity_id}")
            return {
                "links": link_list,
                "total_found": len(link_list),
                "entity_type": entity_type,
                "entity_id": entity_id
            }
            
        except Exception as e:
            logger.error(f"[list_semantic_links] FAILED: {type(e).__name__}: {e}", exc_info=True)
            return {"error": f"{type(e).__name__}: {str(e)}", "links": []}

    async def _tool_remove_semantic_link(
        self,
        link_id: str
    ) -> Dict[str, Any]:
        """Remove a semantic link."""
        logger.info(f"[remove_semantic_link] Starting - link_id={link_id}")
        
        try:
            from src.controller.semantic_links_manager import SemanticLinksManager
            
            # Create manager instance
            manager = SemanticLinksManager(
                db=self._db,
                semantic_models_manager=self._semantic_models_manager
            )
            
            # Remove the link
            success = manager.remove(link_id, removed_by="llm-assistant")
            
            if not success:
                return {
                    "success": False,
                    "error": f"Semantic link '{link_id}' not found"
                }
            
            self._db.commit()
            
            logger.info(f"[remove_semantic_link] SUCCESS: Removed link {link_id}")
            return {
                "success": True,
                "message": f"Semantic link removed successfully",
                "link_id": link_id
            }
            
        except Exception as e:
            logger.error(f"[remove_semantic_link] FAILED: {type(e).__name__}: {e}", exc_info=True)
            self._db.rollback()
            return {"error": f"{type(e).__name__}: {str(e)}"}

