"""
Data Products tools for LLM.

Tools for searching, creating, and updating data products.
"""

import json
import uuid
from typing import Any, Dict, List, Optional

from src.common.logging import get_logger
from src.tools.base import BaseTool, ToolContext, ToolResult

logger = get_logger(__name__)


class SearchDataProductsTool(BaseTool):
    """Search for data products by name, domain, description, or keywords."""
    
    name = "search_data_products"
    description = "Search for data products by name, domain, description, or keywords. Returns matching data products with their metadata."
    parameters = {
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
    }
    required_params = ["query"]
    
    async def execute(
        self,
        ctx: ToolContext,
        query: str,
        domain: Optional[str] = None,
        status: Optional[str] = None
    ) -> ToolResult:
        """Search for data products."""
        logger.info(f"[search_data_products] Starting - query='{query}', domain={domain}, status={status}")
        
        try:
            # Query database directly using the session
            from src.db_models.data_products import DataProductDb
            
            products_db = ctx.db.query(DataProductDb).limit(500).all()
            logger.debug(f"[search_data_products] Found {len(products_db)} total products in database")
            
            if not products_db:
                logger.info(f"[search_data_products] No products found in database")
                return ToolResult(
                    success=True,
                    data={"products": [], "total_found": 0, "message": "No data products found"}
                )
            
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
                        try:
                            desc_dict = json.loads(p.description) if isinstance(p.description, str) else p.description
                            if isinstance(desc_dict, dict):
                                desc_text = desc_dict.get('purpose', '')
                                desc_match = query_lower in desc_text.lower()
                        except Exception:
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
                        try:
                            ports = json.loads(p.output_ports) if isinstance(p.output_ports, str) else p.output_ports
                            if isinstance(ports, list):
                                for port in ports:
                                    if isinstance(port, dict):
                                        output_tables.append(port.get('name', 'Unknown'))
                        except Exception:
                            pass
                    
                    # Extract description purpose from JSON
                    desc_purpose = None
                    if p.description:
                        try:
                            desc_dict = json.loads(p.description) if isinstance(p.description, str) else p.description
                            if isinstance(desc_dict, dict):
                                desc_purpose = desc_dict.get('purpose')
                        except Exception:
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
            return ToolResult(
                success=True,
                data={
                    "products": filtered[:20],  # Limit results
                    "total_found": len(filtered)
                }
            )
            
        except Exception as e:
            logger.error(f"[search_data_products] FAILED: {type(e).__name__}: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
                data={"products": []}
            )


class CreateDraftDataProductTool(BaseTool):
    """Create a new draft data product."""
    
    name = "create_draft_data_product"
    description = "Create a new draft data product. The product will be created in 'draft' status for user review. Optionally link to an existing data contract."
    parameters = {
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
    }
    required_params = ["name", "description", "domain"]
    
    async def execute(
        self,
        ctx: ToolContext,
        name: str,
        description: str,
        domain: str,
        contract_id: Optional[str] = None,
        output_tables: Optional[List[str]] = None
    ) -> ToolResult:
        """Create a draft data product."""
        logger.info(f"[create_draft_data_product] Starting - name='{name}', domain={domain}, contract_id={contract_id}")
        
        if not ctx.data_products_manager:
            logger.error(f"[create_draft_data_product] FAILED: Data products manager not available")
            return ToolResult(success=False, error="Data products manager not available")
        
        try:
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
            created = ctx.data_products_manager.create_product(
                product_data=product_data,
                db=ctx.db
            )
            
            logger.info(f"[create_draft_data_product] SUCCESS: Created product id={created.id}, name={created.name}")
            return ToolResult(
                success=True,
                data={
                    "success": True,
                    "product_id": created.id,
                    "name": created.name,
                    "version": created.version,
                    "status": created.status,
                    "message": f"Draft product '{name}' created successfully. Review and publish it in the Data Products UI.",
                    "url": f"/data-products/{created.id}"
                }
            )
            
        except Exception as e:
            logger.error(f"[create_draft_data_product] FAILED: {type(e).__name__}: {e}", exc_info=True)
            return ToolResult(success=False, error=f"{type(e).__name__}: {str(e)}")


class UpdateDataProductTool(BaseTool):
    """Update an existing data product's properties."""
    
    name = "update_data_product"
    description = "Update an existing data product's properties like domain, description, or status."
    parameters = {
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
    }
    required_params = ["product_id"]
    
    async def execute(
        self,
        ctx: ToolContext,
        product_id: str,
        domain: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None
    ) -> ToolResult:
        """Update an existing data product."""
        logger.info(f"[update_data_product] Starting - product_id={product_id}, domain={domain}, status={status}")
        
        if not ctx.data_products_manager:
            logger.error(f"[update_data_product] FAILED: Data products manager not available")
            return ToolResult(success=False, error="Data products manager not available")
        
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
            
            # Update the product
            updated = ctx.data_products_manager.update_product(
                product_id=product_id,
                product_data_dict=update_data,
                db=ctx.db
            )
            
            if not updated:
                return ToolResult(
                    success=False,
                    error=f"Data product '{product_id}' not found"
                )
            
            logger.info(f"[update_data_product] SUCCESS: Updated product id={updated.id}")
            return ToolResult(
                success=True,
                data={
                    "success": True,
                    "product_id": updated.id,
                    "name": updated.name,
                    "domain": updated.domain,
                    "status": updated.status,
                    "message": f"Product '{updated.name}' updated successfully.",
                    "url": f"/data-products/{updated.id}"
                }
            )
            
        except Exception as e:
            logger.error(f"[update_data_product] FAILED: {type(e).__name__}: {e}", exc_info=True)
            return ToolResult(success=False, error=f"{type(e).__name__}: {str(e)}")

