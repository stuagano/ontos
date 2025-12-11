"""
Data Contracts tools for LLM.

Tools for creating and updating data contracts.
"""

from typing import Any, Dict, List, Optional

from src.common.logging import get_logger
from src.tools.base import BaseTool, ToolContext, ToolResult

logger = get_logger(__name__)


class CreateDraftDataContractTool(BaseTool):
    """Create a new draft data contract based on schema information."""
    
    name = "create_draft_data_contract"
    description = "Create a new draft data contract based on schema information. The contract will be created in 'draft' status for user review. Use after exploring a catalog schema to formalize a data asset."
    parameters = {
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
    }
    required_params = ["name", "description", "domain"]
    
    async def execute(
        self,
        ctx: ToolContext,
        name: str,
        description: str,
        domain: str,
        tables: Optional[List[Dict[str, Any]]] = None
    ) -> ToolResult:
        """Create a draft data contract from schema information."""
        logger.info(f"[create_draft_data_contract] Starting - name='{name}', domain={domain}, tables={len(tables) if tables else 0}")
        
        if not ctx.data_contracts_manager:
            logger.error(f"[create_draft_data_contract] FAILED: Data contracts manager not available")
            return ToolResult(success=False, error="Data contracts manager not available")
        
        try:
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
            created = ctx.data_contracts_manager.create_contract_with_relations(
                db=ctx.db,
                contract_data=contract_data,
                current_user=None  # Will use system default
            )
            
            logger.info(f"[create_draft_data_contract] SUCCESS: Created contract id={created.id}, name={created.name}")
            return ToolResult(
                success=True,
                data={
                    "success": True,
                    "contract_id": created.id,
                    "name": created.name,
                    "version": created.version,
                    "status": created.status,
                    "message": f"Draft contract '{name}' created successfully. Review and publish it in the Data Contracts UI.",
                    "url": f"/data-contracts/{created.id}"
                }
            )
            
        except Exception as e:
            logger.error(f"[create_draft_data_contract] FAILED: {type(e).__name__}: {e}", exc_info=True)
            return ToolResult(success=False, error=f"{type(e).__name__}: {str(e)}")


class UpdateDataContractTool(BaseTool):
    """Update an existing data contract's properties."""
    
    name = "update_data_contract"
    description = "Update an existing data contract's properties like domain, description, or status."
    parameters = {
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
    }
    required_params = ["contract_id"]
    
    async def execute(
        self,
        ctx: ToolContext,
        contract_id: str,
        domain: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None
    ) -> ToolResult:
        """Update an existing data contract."""
        logger.info(f"[update_data_contract] Starting - contract_id={contract_id}, domain={domain}, status={status}")
        
        if not ctx.data_contracts_manager:
            logger.error(f"[update_data_contract] FAILED: Data contracts manager not available")
            return ToolResult(success=False, error="Data contracts manager not available")
        
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
                return ToolResult(
                    success=False,
                    error="No fields to update. Provide at least one of: domain, description, status"
                )
            
            # Update the contract
            updated = ctx.data_contracts_manager.update_contract_with_relations(
                db=ctx.db,
                contract_id=contract_id,
                contract_data=update_data,
                current_user=None
            )
            
            if not updated:
                return ToolResult(
                    success=False,
                    error=f"Data contract '{contract_id}' not found"
                )
            
            logger.info(f"[update_data_contract] SUCCESS: Updated contract id={updated.id}")
            return ToolResult(
                success=True,
                data={
                    "success": True,
                    "contract_id": updated.id,
                    "name": updated.name,
                    "domain": updated.domain,
                    "status": updated.status,
                    "message": f"Contract '{updated.name}' updated successfully.",
                    "url": f"/data-contracts/{updated.id}"
                }
            )
            
        except Exception as e:
            logger.error(f"[update_data_contract] FAILED: {type(e).__name__}: {e}", exc_info=True)
            return ToolResult(success=False, error=f"{type(e).__name__}: {str(e)}")

