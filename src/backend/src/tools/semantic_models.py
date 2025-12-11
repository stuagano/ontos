"""
Semantic Models tools for LLM.

Tools for searching glossary terms and managing semantic links.
"""

from typing import Any, Dict, Optional

from src.common.logging import get_logger
from src.tools.base import BaseTool, ToolContext, ToolResult

logger = get_logger(__name__)


class SearchGlossaryTermsTool(BaseTool):
    """Search the knowledge graph for business concepts, terms, and definitions."""
    
    name = "search_glossary_terms"
    description = "Search the knowledge graph for business concepts, terms, and definitions from ontologies and taxonomies."
    parameters = {
        "term": {
            "type": "string",
            "description": "Business term or concept to search for (e.g., 'Customer', 'Sales', 'Transaction', 'Revenue')"
        },
        "domain": {
            "type": "string",
            "description": "Optional taxonomy/domain filter"
        }
    }
    required_params = ["term"]
    
    async def execute(
        self,
        ctx: ToolContext,
        term: str,
        domain: Optional[str] = None
    ) -> ToolResult:
        """Search for business terms/concepts in the knowledge graph."""
        logger.info(f"[search_glossary_terms] Starting - term='{term}', domain={domain}")
        
        if not ctx.semantic_models_manager:
            logger.warning(f"[search_glossary_terms] FAILED: semantic_models_manager is None")
            return ToolResult(
                success=False,
                error="Knowledge graph not available",
                data={"terms": []}
            )
        
        try:
            # Search concepts in the semantic models / knowledge graph
            # Results are ConceptSearchResult with nested 'concept' (OntologyConcept)
            results = ctx.semantic_models_manager.search_ontology_concepts(term, limit=20)
            
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
            return ToolResult(
                success=True,
                data={
                    "terms": terms[:15],
                    "total_found": len(results),
                    "source": "knowledge_graph"
                }
            )
            
        except Exception as e:
            logger.error(f"[search_glossary_terms] FAILED: {type(e).__name__}: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
                data={"terms": []}
            )


class AddSemanticLinkTool(BaseTool):
    """Link a data product or contract to a business term/concept from the knowledge graph."""
    
    name = "add_semantic_link"
    description = "Link a data product or contract to a business term/concept from the knowledge graph. Use search_glossary_terms first to find the concept IRI."
    parameters = {
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
    }
    required_params = ["entity_type", "entity_id", "concept_iri", "concept_label"]
    
    async def execute(
        self,
        ctx: ToolContext,
        entity_type: str,
        entity_id: str,
        concept_iri: str,
        concept_label: str,
        relationship_type: str = "relatedTo"
    ) -> ToolResult:
        """Add a semantic link from an entity to a knowledge graph concept."""
        logger.info(f"[add_semantic_link] Starting - entity_type={entity_type}, entity_id={entity_id}, concept_iri={concept_iri}")
        
        try:
            from src.controller.semantic_links_manager import SemanticLinksManager
            from src.models.semantic_links import EntitySemanticLinkCreate
            
            # Create manager instance
            manager = SemanticLinksManager(
                db=ctx.db,
                semantic_models_manager=ctx.semantic_models_manager
            )
            
            # Check if link already exists
            existing_links = manager.list_for_entity(entity_id=entity_id, entity_type=entity_type)
            for link in existing_links:
                if link.iri == concept_iri:
                    return ToolResult(
                        success=True,
                        data={
                            "success": True,
                            "message": f"Semantic link to '{concept_label}' already exists for this {entity_type}",
                            "link_id": link.id,
                            "already_linked": True
                        }
                    )
            
            # Create the link
            link_data = EntitySemanticLinkCreate(
                entity_type=entity_type,
                entity_id=entity_id,
                iri=concept_iri,
                label=concept_label,
                relationship_type=relationship_type
            )
            
            created = manager.add(link_data, created_by="llm-assistant")
            ctx.db.commit()
            
            logger.info(f"[add_semantic_link] SUCCESS: Linked {entity_type} {entity_id} to concept '{concept_label}'")
            return ToolResult(
                success=True,
                data={
                    "success": True,
                    "message": f"Linked {entity_type} to business term '{concept_label}'",
                    "link_id": created.id,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "concept_iri": concept_iri,
                    "concept_label": concept_label,
                    "relationship_type": relationship_type
                }
            )
            
        except Exception as e:
            logger.error(f"[add_semantic_link] FAILED: {type(e).__name__}: {e}", exc_info=True)
            ctx.db.rollback()
            return ToolResult(success=False, error=f"{type(e).__name__}: {str(e)}")


class ListSemanticLinksTool(BaseTool):
    """List semantic links (business term associations) for a data product or contract."""
    
    name = "list_semantic_links"
    description = "List semantic links (business term associations) for a data product or contract."
    parameters = {
        "entity_type": {
            "type": "string",
            "description": "Type of entity",
            "enum": ["data_product", "data_contract"]
        },
        "entity_id": {
            "type": "string",
            "description": "ID of the entity"
        }
    }
    required_params = ["entity_type", "entity_id"]
    
    async def execute(
        self,
        ctx: ToolContext,
        entity_type: str,
        entity_id: str
    ) -> ToolResult:
        """List semantic links for an entity."""
        logger.info(f"[list_semantic_links] Starting - entity_type={entity_type}, entity_id={entity_id}")
        
        try:
            from src.controller.semantic_links_manager import SemanticLinksManager
            
            # Create manager instance
            manager = SemanticLinksManager(
                db=ctx.db,
                semantic_models_manager=ctx.semantic_models_manager
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
            return ToolResult(
                success=True,
                data={
                    "links": link_list,
                    "total_found": len(link_list),
                    "entity_type": entity_type,
                    "entity_id": entity_id
                }
            )
            
        except Exception as e:
            logger.error(f"[list_semantic_links] FAILED: {type(e).__name__}: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
                data={"links": []}
            )


class RemoveSemanticLinkTool(BaseTool):
    """Remove a semantic link from a data product or contract."""
    
    name = "remove_semantic_link"
    description = "Remove a semantic link from a data product or contract. Use list_semantic_links first to find the link ID."
    parameters = {
        "link_id": {
            "type": "string",
            "description": "ID of the semantic link to remove (from list_semantic_links)"
        }
    }
    required_params = ["link_id"]
    
    async def execute(
        self,
        ctx: ToolContext,
        link_id: str
    ) -> ToolResult:
        """Remove a semantic link."""
        logger.info(f"[remove_semantic_link] Starting - link_id={link_id}")
        
        try:
            from src.controller.semantic_links_manager import SemanticLinksManager
            
            # Create manager instance
            manager = SemanticLinksManager(
                db=ctx.db,
                semantic_models_manager=ctx.semantic_models_manager
            )
            
            # Remove the link
            success = manager.remove(link_id, removed_by="llm-assistant")
            
            if not success:
                return ToolResult(
                    success=False,
                    error=f"Semantic link '{link_id}' not found"
                )
            
            ctx.db.commit()
            
            logger.info(f"[remove_semantic_link] SUCCESS: Removed link {link_id}")
            return ToolResult(
                success=True,
                data={
                    "success": True,
                    "message": "Semantic link removed successfully",
                    "link_id": link_id
                }
            )
            
        except Exception as e:
            logger.error(f"[remove_semantic_link] FAILED: {type(e).__name__}: {e}", exc_info=True)
            ctx.db.rollback()
            return ToolResult(success=False, error=f"{type(e).__name__}: {str(e)}")

