from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime, timedelta
from rdflib import Graph, ConjunctiveGraph, Dataset
from rdflib.namespace import RDF, RDFS, SKOS, OWL
from rdflib import URIRef, Literal, Namespace, BNode

# Ontos application ontology namespace
ONTOS = Namespace("http://ontos.app/ontology#")

# XSD namespace for datatype handling
from rdflib.namespace import XSD
from sqlalchemy.orm import Session
import signal
from contextlib import contextmanager
import json
import shutil
from filelock import FileLock

from src.db_models.semantic_models import SemanticModelDb
from src.models.semantic_models import (
    SemanticModel as SemanticModelApi,
    SemanticModelCreate,
    SemanticModelUpdate,
    SemanticModelPreview,
)
from src.models.ontology import (
    OntologyConcept,
    OntologyProperty,
    SemanticModel as SemanticModelOntology,
    ConceptHierarchy,
    TaxonomyStats,
    ConceptSearchResult
)
from src.repositories.semantic_models_repository import semantic_models_repo
from src.repositories.rdf_triples_repository import rdf_triples_repo
from src.common.logging import get_logger
from src.common.sparql_validator import SPARQLQueryValidator


logger = get_logger(__name__)


def _sanitize_context_name(name: str) -> str:
    """Sanitize a name for use in URN context identifiers.
    
    Replaces special characters that are problematic in URNs with safe alternatives.
    Preserves human readability while ensuring valid URN syntax.
    
    Args:
        name: The original name (e.g., filename like "my_ontology.ttl")
    
    Returns:
        Sanitized name safe for use in URN (e.g., "my_ontology.ttl")
    """
    import re
    # Replace spaces with underscores
    sanitized = name.replace(' ', '_')
    # Remove or replace characters that are problematic in URNs
    # Keep alphanumeric, underscores, hyphens, and dots
    sanitized = re.sub(r'[^a-zA-Z0-9_.\-]', '_', sanitized)
    # Collapse multiple underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    # Ensure we have a valid name (fallback if empty)
    if not sanitized:
        sanitized = "unnamed"
    return sanitized


@contextmanager
def timeout(seconds: int):
    """Context manager for query timeout using signals.
    
    Note: This only works on Unix-like systems. On Windows, this will
    not enforce a timeout but will still allow the query to execute.
    """
    def timeout_handler(signum, frame):
        raise TimeoutError("Query execution timeout")
    
    # Only set up signal handler on Unix-like systems
    if hasattr(signal, 'SIGALRM'):
        original_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, original_handler)
    else:
        # On Windows or systems without SIGALRM, just yield without timeout
        logger.warning("Query timeout not available on this platform")
        yield


class CachedResult:
    """Simple cache entry with TTL"""
    def __init__(self, value: Any, ttl_seconds: int = 300):
        self.value = value
        self.expires_at = datetime.now() + timedelta(seconds=ttl_seconds)

    def is_valid(self) -> bool:
        return datetime.now() < self.expires_at


class SemanticModelsManager:
    def __init__(self, db: Session, data_dir: Optional[Path] = None):
        self._db = db
        self._data_dir = data_dir or Path(__file__).parent.parent / "data"
        # Use ConjunctiveGraph to support named graphs/contexts
        self._graph = ConjunctiveGraph()
        # Cache for expensive operations (TTL: 5 minutes)
        self._cache: Dict[str, CachedResult] = {}
        logger.info(f"SemanticModelsManager initialized with data_dir: {self._data_dir}")
        # Load file-based taxonomies immediately
        try:
            self.rebuild_graph_from_enabled()
        except Exception as e:
            logger.error(f"Failed to rebuild graph during initialization: {e}")

    def list(self) -> List[SemanticModelApi]:
        items = semantic_models_repo.get_multi(self._db)
        return [self._to_api(m) for m in items]

    def get(self, model_id: str) -> Optional[SemanticModelApi]:
        m = semantic_models_repo.get(self._db, id=model_id)
        return self._to_api(m) if m else None

    def create(self, data: SemanticModelCreate, created_by: Optional[str]) -> SemanticModelApi:
        db_obj = semantic_models_repo.create(self._db, obj_in=data)
        if created_by:
            db_obj.created_by = created_by
            db_obj.updated_by = created_by
            self._db.add(db_obj)
        self._db.flush()
        self._db.refresh(db_obj)
        
        # Import triples to rdf_triples table if content is provided
        if db_obj.content_text:
            try:
                # Use sanitized name for human-readable context identifiers
                sanitized_name = _sanitize_context_name(db_obj.name)
                context_name = f"urn:semantic-model:{sanitized_name}"
                temp_graph = Graph()
                fmt = 'turtle' if db_obj.format == 'skos' else 'xml'
                temp_graph.parse(data=db_obj.content_text, format=fmt)
                self._import_graph_to_db(
                    graph=temp_graph,
                    context_name=context_name,
                    source_type='upload',
                    source_identifier=db_obj.name,
                    created_by=created_by,
                )
            except Exception as e:
                logger.warning(f"Failed to import semantic model triples to database: {e}")
        
        self._db.commit()  # Persist changes immediately since manager uses singleton session
        return self._to_api(db_obj)

    def update(self, model_id: str, update: SemanticModelUpdate, updated_by: Optional[str]) -> Optional[SemanticModelApi]:
        db_obj = semantic_models_repo.get(self._db, id=model_id)
        if not db_obj:
            return None
        updated = semantic_models_repo.update(self._db, db_obj=db_obj, obj_in=update)
        if updated_by:
            updated.updated_by = updated_by
            self._db.add(updated)
        self._db.flush()
        self._db.refresh(updated)
        self._db.commit()  # Persist changes immediately since manager uses singleton session
        return self._to_api(updated)

    def replace_content(self, model_id: str, content_text: str, original_filename: Optional[str], content_type: Optional[str], size_bytes: Optional[int], updated_by: Optional[str]) -> Optional[SemanticModelApi]:
        db_obj = semantic_models_repo.get(self._db, id=model_id)
        if not db_obj:
            return None
        db_obj.content_text = content_text
        if original_filename is not None:
            db_obj.original_filename = original_filename
        if content_type is not None:
            db_obj.content_type = content_type
        if size_bytes is not None:
            db_obj.size_bytes = str(size_bytes)
        if updated_by:
            db_obj.updated_by = updated_by
        self._db.add(db_obj)
        self._db.flush()
        self._db.refresh(db_obj)
        
        # Update rdf_triples: remove old triples, import new ones
        # Use sanitized name for human-readable context identifiers
        sanitized_name = _sanitize_context_name(db_obj.name)
        context_name = f"urn:semantic-model:{sanitized_name}"
        try:
            # Remove existing triples for this model
            rdf_triples_repo.remove_by_context(self._db, context_name)
            
            # Import new triples
            temp_graph = Graph()
            fmt = 'turtle' if db_obj.format == 'skos' else 'xml'
            temp_graph.parse(data=content_text, format=fmt)
            self._import_graph_to_db(
                graph=temp_graph,
                context_name=context_name,
                source_type='upload',
                source_identifier=db_obj.name,
                created_by=updated_by,
            )
        except Exception as e:
            logger.warning(f"Failed to update semantic model triples in database: {e}")
        
        self._db.commit()  # Persist changes immediately since manager uses singleton session
        return self._to_api(db_obj)

    def delete(self, model_id: str) -> bool:
        # Get the model before deleting to check if we need to delete the physical file
        model = semantic_models_repo.get(self._db, id=model_id)
        if not model:
            return False
        
        # If this was loaded from data/semantic_models/ directory, delete the physical file too
        if model.created_by == 'system@startup' and model.original_filename:
            try:
                file_path = self._data_dir / "semantic_models" / model.original_filename
                if file_path.exists() and file_path.is_file():
                    file_path.unlink()
                    logger.info(f"Deleted physical file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to delete physical file for model {model_id}: {e}")
        
        # Delete triples from rdf_triples table
        # Use sanitized name for human-readable context identifiers (consistent with create/replace)
        sanitized_name = _sanitize_context_name(model.name)
        context_name = f"urn:semantic-model:{sanitized_name}"
        try:
            deleted_count = rdf_triples_repo.remove_by_context(self._db, context_name)
            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} triples for semantic model '{model.name}' (context: {context_name})")
        except Exception as e:
            logger.warning(f"Failed to delete triples for semantic model '{model.name}': {e}")
        
        # Delete from database
        obj = semantic_models_repo.remove(self._db, id=model_id)
        self._db.commit()  # Persist changes immediately since manager uses singleton session
        return obj is not None

    def preview(self, model_id: str, max_chars: int = 2000) -> Optional[SemanticModelPreview]:
        db_obj = semantic_models_repo.get(self._db, id=model_id)
        if not db_obj:
            return None
        return SemanticModelPreview(
            id=db_obj.id,
            name=db_obj.name,
            format=db_obj.format,  # type: ignore
            preview=db_obj.content_text[:max_chars] if db_obj.content_text else ""
        )

    def _to_api(self, db_obj: SemanticModelDb) -> SemanticModelApi:
        return SemanticModelApi(
            id=db_obj.id,
            name=db_obj.name,
            format=db_obj.format,  # type: ignore
            original_filename=db_obj.original_filename,
            content_type=db_obj.content_type,
            size_bytes=int(db_obj.size_bytes) if db_obj.size_bytes is not None and str(db_obj.size_bytes).isdigit() else None,
            enabled=db_obj.enabled,
            created_by=db_obj.created_by,
            updated_by=db_obj.updated_by,
            createdAt=db_obj.created_at,
            updatedAt=db_obj.updated_at,
        )

    # --- Graph Management ---
    def _parse_into_graph(self, content_text: str, fmt: str) -> None:
        if fmt == "skos":
            # Common serializations for SKOS examples: turtle
            self._graph.parse(data=content_text, format="turtle")
        else:
            # Assume RDF/XML for RDFS
            self._graph.parse(data=content_text, format="xml")

    def _parse_into_graph_context(self, content_text: str, fmt: str, context: Graph) -> None:
        """Parse content into a specific named graph context"""
        if fmt == "skos":
            context.parse(data=content_text, format="turtle")
        else:
            # Assume RDF/XML for RDFS
            context.parse(data=content_text, format="xml")

    # --- RDF Triple Persistence Methods ---
    
    def _skolemize_bnode(self, bnode: BNode, context_name: str) -> str:
        """Convert a blank node to a stable URI for persistence.
        
        Blank nodes are graph-local identifiers. To persist them, we convert
        them to URIs that include the context name for global uniqueness.
        """
        return f"urn:ontos:bnode:{context_name}:{str(bnode)}"

    def _import_graph_to_db(
        self,
        graph: Graph,
        context_name: str,
        source_type: str,
        source_identifier: str,
        created_by: Optional[str] = None,
    ) -> int:
        """Import all triples from an rdflib graph into the database.
        
        Uses bulk insert with ON CONFLICT DO NOTHING for idempotent imports.
        Blank nodes are skolemized to stable URIs.
        
        Args:
            graph: The rdflib Graph to import
            context_name: Named graph context (e.g., 'urn:taxonomy:databricks_ontology')
            source_type: Type of source ('file', 'upload', 'demo', 'link')
            source_identifier: Identifier for the source (filename, model_id, etc.)
            created_by: User who initiated the import
        
        Returns:
            Number of triples actually inserted (excludes duplicates)
        """
        triples_to_insert = []
        
        for subj, pred, obj in graph:
            # Handle subject (can be URI or blank node)
            if isinstance(subj, BNode):
                subject_uri = self._skolemize_bnode(subj, context_name)
            else:
                subject_uri = str(subj)
            
            predicate_uri = str(pred)
            
            # Handle object (can be URI, blank node, or literal)
            if isinstance(obj, BNode):
                object_value = self._skolemize_bnode(obj, context_name)
                object_is_uri = True
                object_language = None
                object_datatype = None
            elif isinstance(obj, Literal):
                object_value = str(obj)
                object_is_uri = False
                object_language = obj.language if obj.language else None
                object_datatype = str(obj.datatype) if obj.datatype else None
            else:
                # URIRef
                object_value = str(obj)
                object_is_uri = True
                object_language = None
                object_datatype = None
            
            triples_to_insert.append({
                'subject_uri': subject_uri,
                'predicate_uri': predicate_uri,
                'object_value': object_value,
                'object_is_uri': object_is_uri,
                'object_language': object_language,
                'object_datatype': object_datatype,
                'context_name': context_name,
                'source_type': source_type,
                'source_identifier': source_identifier,
                'created_by': created_by,
            })
        
        if triples_to_insert:
            inserted = rdf_triples_repo.add_triples_bulk(self._db, triples_to_insert)
            self._db.commit()
            logger.info(f"Imported {inserted}/{len(triples_to_insert)} triples "
                       f"from {source_type}:{source_identifier} to context '{context_name}'")
            return inserted
        return 0

    def _sync_bundled_taxonomies(self) -> None:
        """Sync bundled taxonomy files from data/taxonomies/ to the database.
        
        Called on every startup. Uses ON CONFLICT DO NOTHING for idempotent
        behavior - existing triples are skipped, new/missing triples are added.
        This allows:
        - First run: imports everything
        - Subsequent runs: fast no-op for existing triples
        - New files added: automatically imported
        - Partial DB: self-healing backfill
        """
        taxonomy_dir = self._data_dir / "taxonomies"
        
        if not taxonomy_dir.exists() or not taxonomy_dir.is_dir():
            logger.warning(f"Taxonomy directory does not exist: {taxonomy_dir}")
            return
        
        taxonomy_files = list(taxonomy_dir.glob("*.ttl"))
        logger.info(f"Syncing {len(taxonomy_files)} bundled taxonomy files to database")
        
        for f in taxonomy_files:
            if not f.is_file():
                continue
            
            context_name = f"urn:taxonomy:{f.stem}"
            
            try:
                # Parse the TTL file into a temporary graph
                temp_graph = Graph()
                temp_graph.parse(f.as_posix(), format='turtle')
                triple_count = len(temp_graph)
                
                # Import to database (idempotent with ON CONFLICT DO NOTHING)
                inserted = self._import_graph_to_db(
                    graph=temp_graph,
                    context_name=context_name,
                    source_type='file',
                    source_identifier=f.name,
                    created_by='system@startup',
                )
                
                if inserted > 0:
                    logger.info(f"Synced taxonomy '{f.name}': {inserted} new triples "
                               f"(total in file: {triple_count})")
                else:
                    logger.debug(f"Taxonomy '{f.name}' already synced ({triple_count} triples)")
                    
            except Exception as e:
                logger.error(f"Failed to sync taxonomy {f.name}: {e}")

    def _load_triples_from_db_to_graph(self) -> None:
        """Load all triples from the database into the in-memory graph.
        
        This replaces direct file loading - the database is now the source of truth.
        Triples are organized into named graph contexts based on their context_name.
        """
        all_triples = rdf_triples_repo.list_all(self._db)
        logger.info(f"Loading {len(all_triples)} triples from database into graph")
        
        for triple in all_triples:
            context = self._graph.get_context(triple.context_name)
            
            subj = URIRef(triple.subject_uri)
            pred = URIRef(triple.predicate_uri)
            
            if triple.object_is_uri:
                obj = URIRef(triple.object_value)
            else:
                # It's a literal
                if triple.object_language:
                    obj = Literal(triple.object_value, lang=triple.object_language)
                elif triple.object_datatype:
                    obj = Literal(triple.object_value, datatype=URIRef(triple.object_datatype))
                else:
                    obj = Literal(triple.object_value)
            
            context.add((subj, pred, obj))
        
        # Log stats by context
        contexts = rdf_triples_repo.list_contexts(self._db)
        for ctx in contexts:
            count = rdf_triples_repo.count_by_context(self._db, ctx)
            logger.debug(f"Loaded context '{ctx}': {count} triples")

    def _load_database_glossaries_into_graph(self) -> None:
        """Load database glossaries as RDF triples into named graphs"""
        try:
            # We'll need to import the business glossaries manager to avoid circular imports
            # For now, we'll defer this implementation
            logger.debug("Database glossary loading will be implemented when business glossaries manager is updated")
        except Exception as e:
            logger.warning(f"Failed to load database glossaries into graph: {e}")

    def rebuild_graph_from_enabled(self) -> None:
        """Rebuild the in-memory RDF graph from database and dynamic sources.
        
        The database (rdf_triples table) is the source of truth for:
        - Bundled taxonomies (synced from data/taxonomies/ on startup)
        - User-uploaded ontologies
        - Demo data
        - Semantic links
        
        Dynamic sources (computed, not stored):
        - Application entities (data domains, data products, data contracts)
        - Database glossaries
        """
        logger.info("Starting to rebuild graph from database and dynamic sources")
        self._graph = ConjunctiveGraph()
        
        # Step 1: Sync bundled taxonomy files to database (idempotent)
        # This ensures any new/missing files are imported
        try:
            self._sync_bundled_taxonomies()
        except Exception as e:
            logger.error(f"Failed to sync bundled taxonomies: {e}")
        
        # Step 2: Load all triples from database into in-memory graph
        # This includes: taxonomies, user uploads, demo data, semantic links
        try:
            self._load_triples_from_db_to_graph()
        except Exception as e:
            logger.error(f"Failed to load triples from database: {e}")
        
        # Step 3: Load database-backed semantic models (legacy support)
        # These are models stored as content_text in semantic_models table
        # TODO: Migrate these to rdf_triples table as well
        items = semantic_models_repo.get_multi(self._db)
        for it in items:
            if not it.enabled:
                continue
            try:
                # Use sanitized name for human-readable context identifiers
                sanitized_name = _sanitize_context_name(it.name)
                context_name = f"urn:semantic-model:{sanitized_name}"
                context = self._graph.get_context(context_name)
                self._parse_into_graph_context(it.content_text or "", it.format, context)
                logger.debug(f"Loaded semantic model '{it.name}' into context '{context_name}'")
            except Exception as e:
                logger.warning(f"Skipping model '{it.name}' due to parse error: {e}")
        
        # Step 4: Load application entities (dynamically computed, not stored)
        try:
            self._load_app_entities_into_graph()
        except Exception as e:
            logger.warning(f"Failed to load application entities into graph: {e}")
        
        # Step 5: Load database glossaries (dynamically computed)
        self._load_database_glossaries_into_graph()
        
        # Note: Semantic links are now loaded from rdf_triples in Step 2
        # The entity_semantic_links table is kept as a denormalized index
        # but triples are also persisted to rdf_triples via dual-write

        # Build persistent caches after graph is rebuilt
        try:
            self._build_persistent_caches_atomic()
        except Exception as e:
            logger.error(f"Failed to build persistent caches: {e}", exc_info=True)

    def _build_persistent_caches_atomic(self) -> None:
        """Build and save persistent caches atomically to disk.

        Uses atomic directory swap to prevent partial cache reads.
        Cache files are JSON-serialized for fast loading.
        """
        cache_dir = self._data_dir / "cache"
        temp_dir = self._data_dir / "cache_building"
        lock_file = self._data_dir / "cache" / "rebuild.lock"

        # Ensure lock directory exists
        lock_file.parent.mkdir(parents=True, exist_ok=True)

        # Prevent concurrent cache builds
        with FileLock(str(lock_file), timeout=300):
            logger.info("Building persistent caches...")

            # Clean temp directory
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            temp_dir.mkdir(parents=True)

            try:
                # Build all caches in temp directory
                # 1. All concepts
                logger.info("Computing all concepts for cache...")
                all_concepts = self._compute_all_concepts()
                concepts_data = [c.model_dump() for c in all_concepts]
                with open(temp_dir / "concepts_all.json", "w") as f:
                    json.dump(concepts_data, f)
                logger.info(f"Cached {len(all_concepts)} concepts")

                # 2. Taxonomies
                logger.info("Computing taxonomies for cache...")
                taxonomies = self._compute_taxonomies()
                taxonomies_data = [t.model_dump() for t in taxonomies]
                with open(temp_dir / "taxonomies.json", "w") as f:
                    json.dump(taxonomies_data, f)
                logger.info(f"Cached {len(taxonomies)} taxonomies")

                # 3. Stats (depends on concepts and taxonomies)
                logger.info("Computing stats for cache...")
                stats = self._compute_stats(all_concepts, taxonomies)
                with open(temp_dir / "stats.json", "w") as f:
                    json.dump(stats.model_dump(), f)
                logger.info("Cached stats")

                # Atomic swap: move temp files to final location
                cache_dir.mkdir(parents=True, exist_ok=True)
                for file in temp_dir.glob("*.json"):
                    final_path = cache_dir / file.name
                    # Remove old file if exists
                    if final_path.exists():
                        final_path.unlink()
                    # Move new file
                    file.rename(final_path)

                # Remove temp directory
                temp_dir.rmdir()

                logger.info("Persistent caches built successfully")

            except Exception as e:
                # Clean up temp directory on failure
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                raise

    def _compute_taxonomies(self) -> List:
        """Compute taxonomies without caching - used for building persistent cache"""
        from src.models.ontology import SemanticModel as SemanticModelOntology

        taxonomies = []

        # Check if graph has any triples
        total_triples = len(self._graph)
        context_count = len(list(self._graph.contexts()))
        logger.info(f"Graph has {total_triples} total triples and {context_count} contexts")

        # Get contexts from the graph
        for context in self._graph.contexts():
            logger.debug(f"Processing context: {context} (type: {type(context)})")

            # Get the context identifier
            if hasattr(context, 'identifier'):
                context_id = context.identifier
            else:
                logger.debug(f"Context has no identifier attribute: {context}")
                continue

            if not isinstance(context_id, URIRef):
                logger.debug(f"Context identifier is not URIRef: {context_id} ({type(context_id)})")
                continue

            context_str = str(context_id)
            logger.debug(f"Processing context with identifier: {context_str}")

            # Count concepts and properties in this context
            try:
                class_count_query = """
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                SELECT (COUNT(DISTINCT ?concept) AS ?count) WHERE {
                    {
                        ?concept a rdfs:Class .
                    } UNION {
                        ?concept a skos:Concept .
                    } UNION {
                        ?concept a skos:ConceptScheme .
                    } UNION {
                        ?concept a owl:Class .
                    } UNION {
                        # Include any resource that is used as a class (has instances or subclasses)
                        ?concept rdfs:subClassOf ?parent .
                    } UNION {
                        ?instance a ?concept .
                        FILTER(?concept != rdfs:Class && ?concept != skos:Concept && ?concept != rdf:Property && ?concept != owl:Class)
                    } UNION {
                        # Include resources with semantic properties that make them conceptual
                        ?concept rdfs:label ?someLabel .
                        ?concept rdfs:comment ?someComment .
                    }
                    # Filter out basic RDF/RDFS/SKOS/OWL vocabulary terms
                    FILTER(!STRSTARTS(STR(?concept), "http://www.w3.org/1999/02/22-rdf-syntax-ns#"))
                    FILTER(!STRSTARTS(STR(?concept), "http://www.w3.org/2000/01/rdf-schema#"))
                    FILTER(!STRSTARTS(STR(?concept), "http://www.w3.org/2004/02/skos/core#"))
                    FILTER(!STRSTARTS(STR(?concept), "http://www.w3.org/2002/07/owl#"))
                }
                """

                count_results = list(context.query(class_count_query))
                concepts_count = int(count_results[0][0]) if count_results and count_results[0][0] is not None else 0

                properties_count = len(list(context.subjects(RDF.type, RDF.Property)))

                logger.debug(f"Context {context_str}: {concepts_count} concepts, {properties_count} properties")

            except Exception as e:
                logger.warning(f"Error counting concepts in context {context_str}: {e}")
                concepts_count = 0
                properties_count = 0

            # Determine taxonomy type and name
            if context_str.startswith("urn:taxonomy:"):
                source_type = "file"
                name = context_str.replace("urn:taxonomy:", "")
                format_str = "ttl"
            elif context_str.startswith("urn:semantic-model:"):
                source_type = "database"
                name = context_str.replace("urn:semantic-model:", "")
                format_str = "rdfs"
            elif context_str.startswith("urn:schema:"):
                source_type = "schema"
                name = context_str.replace("urn:schema:", "")
                format_str = "ttl"
            elif context_str.startswith("urn:glossary:"):
                source_type = "database"
                name = context_str.replace("urn:glossary:", "")
                format_str = "rdfs"
            else:
                source_type = "external"
                name = context_str
                format_str = None

            taxonomies.append(SemanticModelOntology(
                name=name,
                description=f"{source_type.title()} taxonomy: {name}",
                source_type=source_type,
                format=format_str,
                concepts_count=concepts_count,
                properties_count=properties_count
            ))

        return sorted(taxonomies, key=lambda t: (t.source_type, t.name))

    def _compute_stats(self, all_concepts: List, taxonomies: List) -> Any:
        """Compute stats without caching - used for building persistent cache"""
        from src.models.ontology import TaxonomyStats

        total_concepts = sum(t.concepts_count for t in taxonomies)
        total_properties = sum(t.properties_count for t in taxonomies)

        # Get concepts by type
        concepts_by_type = {}
        for concept in all_concepts:
            concept_type = concept.concept_type
            concepts_by_type[concept_type] = concepts_by_type.get(concept_type, 0) + 1

        # Count top-level concepts (those without parents)
        top_level_concepts = sum(1 for concept in all_concepts if not concept.parent_concepts)

        return TaxonomyStats(
            total_concepts=total_concepts,
            total_properties=total_properties,
            taxonomies=taxonomies,
            concepts_by_type=concepts_by_type,
            top_level_concepts=top_level_concepts
        )

    # Call after create/update/delete/enable/disable
    def on_models_changed(self) -> None:
        try:
            self.rebuild_graph_from_enabled()
            # Invalidate cache when models change
            self._invalidate_cache()
        except Exception as e:
            logger.error(f"Failed to rebuild RDF graph: {e}")

    def _invalidate_cache(self) -> None:
        """Clear all cache entries"""
        self._cache.clear()
        logger.debug("Semantic models cache invalidated")

    def _get_cached(self, key: str) -> Optional[Any]:
        """Get cached value if still valid"""
        if key in self._cache:
            cached = self._cache[key]
            if cached.is_valid():
                logger.debug(f"Cache hit for key: {key}")
                return cached.value
            else:
                logger.debug(f"Cache expired for key: {key}")
                del self._cache[key]
        return None

    def _set_cached(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Store value in cache with TTL"""
        self._cache[key] = CachedResult(value, ttl_seconds)
        logger.debug(f"Cached value for key: {key} (TTL: {ttl_seconds}s)")

    def query(self, sparql: str, max_results: int = 1000, timeout_seconds: int = 30) -> List[dict]:
        """Execute a SPARQL query with security and safety constraints.
        
        Args:
            sparql: The SPARQL query string
            max_results: Maximum number of results to return (default: 1000)
            timeout_seconds: Query execution timeout in seconds (default: 30)
            
        Returns:
            List of result dictionaries
            
        Raises:
            ValueError: If query validation fails or execution times out
        """
        # Validate query first
        validation_error = SPARQLQueryValidator.validate(sparql)
        if validation_error:
            logger.warning(f"SPARQL query validation failed: {validation_error}")
            raise ValueError(f"Invalid SPARQL query: {validation_error}")
        
        # Log sanitized query for security auditing
        sanitized = SPARQLQueryValidator.sanitize_for_logging(sparql)
        logger.info(f"Executing validated SPARQL query: {sanitized}")
        
        results = []
        try:
            # Execute with timeout (Unix-like systems only)
            with timeout(timeout_seconds):
                qres = self._graph.query(sparql)
                
                # Limit results to prevent memory exhaustion
                for idx, row in enumerate(qres):
                    if idx >= max_results:
                        logger.warning(f"Query results truncated at {max_results} rows")
                        break
                    
                    # rdflib QueryResult rows are tuple-like
                    result_row = {}
                    for var_idx, var in enumerate(qres.vars):
                        key = str(var)
                        val = row[var_idx]
                        result_row[key] = str(val) if val is not None else None
                    results.append(result_row)
                
                logger.info(f"SPARQL query completed successfully, returned {len(results)} results")
                
        except TimeoutError:
            logger.error(f"SPARQL query timeout after {timeout_seconds} seconds")
            raise ValueError(f"Query execution timeout - query too expensive (limit: {timeout_seconds}s)")
        except Exception as e:
            logger.error(f"SPARQL query execution error: {e}", exc_info=True)
            raise ValueError(f"Query execution failed: {str(e)}")
        
        return results

    # Simple prefix search over resources and properties (case-insensitive contains)
    def prefix_search(self, prefix: str, limit: int = 20) -> List[dict]:
        q = prefix.lower()
        seen = set()
        results: List[dict] = []
        for s, p, o in self._graph:
            for term, kind in ((s, 'resource'), (p, 'property')):
                if term is None:
                    continue
                name = str(term)
                if q in name.lower() and name not in seen:
                    results.append({ 'value': name, 'type': kind })
                    seen.add(name)
                    if len(results) >= limit:
                        return results
        return results

    # Search for classes/concepts with optional text filter
    def search_concepts(self, text_filter: str = "", limit: int = 50) -> List[dict]:
        sparql_query = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        SELECT DISTINCT ?class_iri ?label
        WHERE {{
            {{
                ?class_iri a rdfs:Class .
            }}
            UNION
            {{
                ?class_iri rdfs:subClassOf ?other .
            }}
            UNION
            {{
                ?class_iri a skos:Concept .
            }}
            UNION
            {{
                ?class_iri a owl:Class .
            }}
            OPTIONAL {{ ?class_iri rdfs:label ?label }}
            OPTIONAL {{ ?class_iri skos:prefLabel ?label }}
            {f'FILTER(CONTAINS(LCASE(STR(?class_iri)), LCASE("{text_filter}")) || CONTAINS(LCASE(STR(?label)), LCASE("{text_filter}")))' if text_filter.strip() else ''}
        }}
        ORDER BY ?class_iri
        LIMIT {limit}
        """
        
        try:
            raw_results = self.query(sparql_query)
            results = []
            for row in raw_results:
                class_iri = row.get('class_iri', '')
                label = row.get('label', '')
                
                # Use label if available, otherwise extract last part of IRI
                if label and label.strip():
                    display_name = label.strip()
                else:
                    # Extract the last segment after # or /
                    if '#' in class_iri:
                        display_name = class_iri.split('#')[-1]
                    elif '/' in class_iri:
                        display_name = class_iri.split('/')[-1]
                    else:
                        display_name = class_iri
                
                results.append({
                    'value': class_iri,
                    'label': display_name,
                    'type': 'class'
                })
            
            return results
        except Exception as e:
            # If SPARQL fails, fall back to empty results
            return []

    def search_properties(self, text_filter: str = "", limit: int = 50) -> List[dict]:
        """Search for properties in the semantic models using SPARQL.

        Returns:
        - OWL properties (owl:ObjectProperty, owl:DatatypeProperty)
        - RDFS properties (rdfs:Property)
        """
        sparql_query = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        SELECT DISTINCT ?property_iri ?label
        WHERE {{
            {{
                ?property_iri a owl:ObjectProperty .
            }}
            UNION
            {{
                ?property_iri a owl:DatatypeProperty .
            }}
            UNION
            {{
                ?property_iri a rdfs:Property .
            }}
            OPTIONAL {{ ?property_iri rdfs:label ?label }}
            {f'FILTER(CONTAINS(LCASE(STR(?property_iri)), LCASE("{text_filter}")) || CONTAINS(LCASE(STR(?label)), LCASE("{text_filter}")))' if text_filter.strip() else ''}
        }}
        ORDER BY ?property_iri
        LIMIT {limit}
        """

        try:
            raw_results = self.query(sparql_query)
            results = []
            for row in raw_results:
                property_iri = row.get('property_iri', '')
                label = row.get('label', '')

                # Use label if available, otherwise extract last part of IRI
                if label and label.strip():
                    display_name = label.strip()
                else:
                    # Extract the last segment after # or /
                    if '#' in property_iri:
                        display_name = property_iri.split('#')[-1]
                    elif '/' in property_iri:
                        display_name = property_iri.split('/')[-1]
                    else:
                        display_name = property_iri

                results.append({
                    'value': property_iri,
                    'label': display_name,
                    'type': 'property'
                })

            return results
        except Exception as e:
            # If SPARQL fails, fall back to empty results
            return []

    def get_child_concepts(self, parent_iri: str, limit: int = 10) -> List[dict]:
        """Get child concepts of a given parent concept for suggestions."""
        if not parent_iri:
            return []
            
        try:
            parent_concept = self.get_concept_details(parent_iri)
            if not parent_concept or not parent_concept.child_concepts:
                return []
            
            # Convert child concept IRIs to the format expected by the dialog
            results = []
            for child_iri in parent_concept.child_concepts[:limit]:
                child_concept = self.get_concept_details(child_iri)
                if child_concept:
                    results.append({
                        'value': child_iri,
                        'label': child_concept.label,
                        'type': 'class'
                    })
            
            return results
        except Exception as e:
            logger.error(f"Failed to get child concepts for {parent_iri}: {e}")
            return []

    def find_best_ancestor_concept_iri(self, parent_iris: List[str]) -> str:
        """Find the first parent IRI in the hierarchy that has child concepts available."""
        if not parent_iris:
            return ""
        
        for parent_iri in parent_iris:
            if parent_iri:
                try:
                    child_concepts = self.get_child_concepts(parent_iri, limit=1)
                    if child_concepts:
                        return parent_iri
                except Exception as e:
                    logger.debug(f"Failed to get child concepts for {parent_iri}: {e}")
                    continue
        
        return ""

    def search_concepts_with_suggestions(self, text_filter: str = "", parent_iris: List[str] = None, limit: int = 50) -> dict:
        """Search for concepts with suggested child concepts first if parent_iris is provided.
        
        Args:
            text_filter: Text filter for concept search
            parent_iris: List of parent concept IRIs in hierarchy order (nearest first)
            limit: Maximum number of results to return
        """
        suggested = []
        other_results = []
        
        # Find the best parent concept from the hierarchy
        if parent_iris:
            best_parent_iri = self.find_best_ancestor_concept_iri(parent_iris)
            if best_parent_iri:
                suggested = self.get_child_concepts(best_parent_iri, limit=10)
        
        # Get all matching concepts
        all_results = self.search_concepts(text_filter, limit=limit)
        
        # Filter out suggested concepts from other results
        suggested_iris = {result['value'] for result in suggested}
        other_results = [result for result in all_results if result['value'] not in suggested_iris]
        
        return {
            'suggested': suggested,
            'other': other_results
        }

    def search_properties_with_suggestions(self, text_filter: str = "", parent_iris: List[str] = None, limit: int = 50) -> dict:
        """Search for properties with suggested child properties first if parent_iris is provided.

        Args:
            text_filter: Text filter for property search
            parent_iris: List of parent concept IRIs in hierarchy order (nearest first)
            limit: Maximum number of results to return
        """
        # For properties, we don't typically have parent-child hierarchies like concepts,
        # so we'll return empty suggestions and all properties as "other"
        suggested = []

        # Get all matching properties
        all_results = self.search_properties(text_filter, limit=limit)

        return {
            'suggested': suggested,
            'other': all_results
        }

    # Outgoing neighbors of a resource: returns distinct predicate/object pairs
    def neighbors(self, resource_iri: str, limit: int = 200) -> List[dict]:
        from rdflib import URIRef
        from rdflib.namespace import RDF
        results: List[dict] = []
        seen: set[tuple[str, str, str]] = set()  # (direction, predicate, display)
        count = 0
        uri = URIRef(resource_iri)

        def detect_type(node: any) -> str:
            if not isinstance(node, URIRef):
                return 'literal'
            try:
                for _ in self._graph.triples((None, node, None)):
                    return 'property'
            except Exception:
                pass
            try:
                for _ in self._graph.triples((node, RDF.type, RDF.Property)):
                    return 'property'
            except Exception:
                pass
            return 'resource'

        def add(direction: str, predicate, display_node, step_node):
            nonlocal count
            display_str = str(display_node)
            key = (direction, str(predicate), display_str)
            if key in seen:
                return
            seen.add(key)
            item = {
                'direction': direction,
                'predicate': str(predicate),
                'display': display_str,
                'displayType': detect_type(display_node),
                'stepIri': str(step_node) if isinstance(step_node, URIRef) else None,
                'stepIsResource': isinstance(step_node, URIRef),
            }
            results.append(item)
            count += 1

        # 1) Outgoing (uri as subject) → show object
        for _, p, o in self._graph.triples((uri, None, None)):
            if count >= limit:
                break
            add('outgoing', p, o, o)

        # 2) Incoming (uri as object) → show subject
        for s, p, _ in self._graph.triples((None, None, uri)):
            if count >= limit:
                break
            add('incoming', p, s, s)

        # 3) Predicate usage (uri as predicate) → show both subject and object entries
        for s, _, o in self._graph.triples((None, uri, None)):
            if count >= limit:
                break
            add('predicate', uri, s, s)
            if count >= limit:
                break
            add('predicate', uri, o, o)

        return results

    # --- App Entities & Incremental Link Updates ---

    def _load_app_entities_into_graph(self) -> None:
        """Load core application entities into the RDF graph with labels/types.

        Adds triples into the 'urn:app-entities' named graph so they persist across rebuilds.
        """
        from sqlalchemy import text as sql_text
        from rdflib.namespace import RDF

        context = self._graph.get_context("urn:app-entities")

        # Data Domains: table data_domains(id, name)
        try:
            rows = self._db.execute(sql_text("SELECT id, name FROM data_domains")).fetchall()
            for r in rows:
                subj = URIRef(f"urn:ontos:data_domain:{r[0]}")
                context.add((subj, RDF.type, URIRef("urn:ontos:entity-type:data_domain")))
                if r[1]:
                    context.add((subj, RDFS.label, Literal(str(r[1]))))
        except Exception as e:
            logger.debug(f"Skipping data domains load into graph: {e}")

        # Data Products: ODPS v1.0.0 schema - use data_products table with id and name fields
        try:
            rows = self._db.execute(sql_text("SELECT id, name FROM data_products")).fetchall()
            for r in rows:
                subj = URIRef(f"urn:ontos:data_product:{r[0]}")
                context.add((subj, RDF.type, URIRef("urn:ontos:entity-type:data_product")))
                if r[1]:
                    context.add((subj, RDFS.label, Literal(str(r[1]))))
        except Exception as e:
            logger.debug(f"Skipping data products load into graph: {e}")

        # Data Contracts: table data_contracts(id, name)
        try:
            rows = self._db.execute(sql_text("SELECT id, name FROM data_contracts")).fetchall()
            for r in rows:
                subj = URIRef(f"urn:ontos:data_contract:{r[0]}")
                # Add both internal type and ODCS standard type
                context.add((subj, RDF.type, URIRef("urn:ontos:entity-type:data_contract")))
                context.add((subj, RDF.type, URIRef("http://odcs.bitol.io/terms#DataContract")))
                if r[1]:
                    context.add((subj, RDFS.label, Literal(str(r[1]))))
        except Exception as e:
            logger.debug(f"Skipping data contracts load into graph: {e}")

    def add_entity_semantic_link_to_graph(self, entity_type: str, entity_id: str, iri: str, created_by: Optional[str] = None) -> None:
        """Incrementally add a single semantic link triple into the graph and database.
        
        Dual-write: Updates both the in-memory graph AND persists to rdf_triples table.
        The entity_semantic_links table is the primary record (written by SemanticLinksManager),
        this ensures the triple is also in rdf_triples for graph queries.
        """
        context_name = "urn:semantic-links"
        subject_uri = f"urn:ontos:{entity_type}:{entity_id}"
        predicate_uri = str(ONTOS.semanticAssignment)
        
        # Add to in-memory graph
        try:
            context = self._graph.get_context(context_name)
            subj = URIRef(subject_uri)
            obj = URIRef(iri)
            context.add((subj, ONTOS.semanticAssignment, obj))
        except Exception as e:
            logger.warning(f"Failed to add semantic link to in-memory graph: {e}")
        
        # Persist to database (dual-write)
        try:
            rdf_triples_repo.add_triple(
                db=self._db,
                subject_uri=subject_uri,
                predicate_uri=predicate_uri,
                object_value=iri,
                object_is_uri=True,
                context_name=context_name,
                source_type='link',
                source_identifier=f"{entity_type}:{entity_id}",
                created_by=created_by,
            )
            self._db.commit()
        except Exception as e:
            logger.warning(f"Failed to persist semantic link to database: {e}")

    def remove_entity_semantic_link_from_graph(self, entity_type: str, entity_id: str, iri: str) -> None:
        """Incrementally remove a single semantic link triple from the graph and database.
        
        Dual-write: Removes from both the in-memory graph AND rdf_triples table.
        """
        context_name = "urn:semantic-links"
        subject_uri = f"urn:ontos:{entity_type}:{entity_id}"
        predicate_uri = str(ONTOS.semanticAssignment)
        
        # Remove from in-memory graph
        try:
            context = self._graph.get_context(context_name)
            subj = URIRef(subject_uri)
            obj = URIRef(iri)
            context.remove((subj, ONTOS.semanticAssignment, obj))
        except Exception as e:
            logger.warning(f"Failed to remove semantic link from in-memory graph: {e}")
        
        # Remove from database (dual-write)
        try:
            rdf_triples_repo.remove_triple(
                db=self._db,
                subject_uri=subject_uri,
                predicate_uri=predicate_uri,
                object_value=iri,
                context_name=context_name,
            )
            self._db.commit()
        except Exception as e:
            logger.warning(f"Failed to remove semantic link from database: {e}")

    # --- New Ontology Methods ---
    
    def get_taxonomies(self) -> List[SemanticModelOntology]:
        """Get all available taxonomies/ontologies with their metadata"""
        # Check persistent cache first
        cache_file = self._data_dir / "cache" / "taxonomies.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                    return [SemanticModelOntology(**item) for item in data]
            except Exception as e:
                logger.warning(f"Failed to load taxonomies from persistent cache: {e}")

        # Fallback to live computation
        logger.warning("Persistent cache not found for taxonomies, computing live")
        taxonomies = self._compute_taxonomies()
        return taxonomies

    def _compute_all_concepts(self, taxonomy_name: str = None) -> List[OntologyConcept]:
        """Compute all concepts without caching - used for building persistent cache"""
        concepts = []

        # Determine which contexts to search
        contexts_to_search = []
        if taxonomy_name:
            # Find the specific context
            target_contexts = [
                f"urn:taxonomy:{taxonomy_name}",
                f"urn:semantic-model:{taxonomy_name}",
                f"urn:schema:{taxonomy_name}",
                f"urn:glossary:{taxonomy_name}"
            ]
            for context in self._graph.contexts():
                if hasattr(context, 'identifier') and str(context.identifier) in target_contexts:
                    contexts_to_search.append((str(context.identifier), context))
        else:
            # Search all contexts
            contexts_to_search = [(str(context.identifier), context)
                                for context in self._graph.contexts()
                                if hasattr(context, 'identifier')]

        for context_name, context in contexts_to_search:
            # Find all classes and concepts in this context - expanded to catch all defined resources
            class_query = """
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            SELECT DISTINCT ?concept ?label ?comment WHERE {
                {
                    ?concept a rdfs:Class .
                } UNION {
                    ?concept a skos:Concept .
                } UNION {
                    ?concept a skos:ConceptScheme .
                } UNION {
                    ?concept a owl:Class .
                } UNION {
                    # Include any resource that is used as a class (has instances or subclasses)
                    ?concept rdfs:subClassOf ?parent .
                } UNION {
                    ?instance a ?concept .
                    FILTER(?concept != rdfs:Class && ?concept != skos:Concept && ?concept != rdf:Property && ?concept != owl:Class)
                } UNION {
                    # Include resources with semantic properties that make them conceptual
                    ?concept rdfs:label ?someLabel .
                    ?concept rdfs:comment ?someComment .
                }
                # Extract labels with priority: skos:prefLabel > rdfs:label
                # Use STR() to handle language tags properly
                OPTIONAL { ?concept skos:prefLabel ?skos_pref_label }
                OPTIONAL { ?concept rdfs:label ?rdfs_label }
                BIND(COALESCE(STR(?skos_pref_label), STR(?rdfs_label)) AS ?label)

                # Extract comments/definitions with priority: skos:definition > rdfs:comment
                OPTIONAL { ?concept skos:definition ?skos_definition }
                OPTIONAL { ?concept rdfs:comment ?rdfs_comment }
                BIND(COALESCE(STR(?skos_definition), STR(?rdfs_comment)) AS ?comment)

                # Filter out basic RDF/RDFS/SKOS/OWL vocabulary terms
                FILTER(!STRSTARTS(STR(?concept), "http://www.w3.org/1999/02/22-rdf-syntax-ns#"))
                FILTER(!STRSTARTS(STR(?concept), "http://www.w3.org/2000/01/rdf-schema#"))
                FILTER(!STRSTARTS(STR(?concept), "http://www.w3.org/2004/02/skos/core#"))
                FILTER(!STRSTARTS(STR(?concept), "http://www.w3.org/2002/07/owl#"))
            }
            ORDER BY ?concept
            """

            try:
                results = context.query(class_query)
                results_list = list(results)
                logger.debug(f"SPARQL query returned {len(results_list)} results for context {context_name}")

                # Process results
                results = results_list
                for row in results:
                    logger.debug(f"Processing SPARQL row: {row} (type: {type(row)}, length: {len(row) if hasattr(row, '__len__') else 'N/A'})")

                    # Handle different ways SPARQL results can be accessed
                    try:
                        if hasattr(row, 'concept'):
                            concept_iri = str(row.concept)
                            label = str(row.label) if hasattr(row, 'label') and row.label else None
                            comment = str(row.comment) if hasattr(row, 'comment') and row.comment else None
                        else:
                            # Fallback to index-based access
                            concept_iri = str(row[0]) if len(row) > 0 else None
                            label = str(row[1]) if len(row) > 1 and row[1] else None
                            comment = str(row[2]) if len(row) > 2 and row[2] else None
                    except Exception as e:
                        logger.warning(f"Failed to parse SPARQL result row {row}: {e}")
                        continue

                    if not concept_iri:
                        logger.debug("Skipping row with no concept IRI")
                        continue

                    concept_uri = URIRef(concept_iri)

                    # Determine concept type
                    if (concept_uri, RDF.type, RDFS.Class) in context:
                        concept_type = "class"
                    elif (concept_uri, RDF.type, OWL.Class) in context:
                        concept_type = "class"
                    elif (concept_uri, RDF.type, SKOS.Concept) in context:
                        concept_type = "concept"
                    else:
                        concept_type = "individual"

                    # Get parent concepts
                    parent_concepts = []
                    # Handle rdfs:subClassOf relationships (class-to-class)
                    for parent in context.objects(concept_uri, RDFS.subClassOf):
                        parent_concepts.append(str(parent))
                    # Handle SKOS broader relationships
                    for parent in context.objects(concept_uri, SKOS.broader):
                        parent_concepts.append(str(parent))
                    # Handle rdf:type relationships (instance-to-class)
                    for parent_type in context.objects(concept_uri, RDF.type):
                        # Only include custom types, not basic RDF/RDFS/SKOS types
                        parent_type_str = str(parent_type)
                        if not any(parent_type_str.startswith(prefix) for prefix in [
                            "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
                            "http://www.w3.org/2000/01/rdf-schema#",
                            "http://www.w3.org/2004/02/skos/core#"
                        ]):
                            parent_concepts.append(parent_type_str)

                    # Extract source context name
                    source_context = None
                    if context_name.startswith("urn:taxonomy:"):
                        source_context = context_name.replace("urn:taxonomy:", "")
                    elif context_name.startswith("urn:semantic-model:"):
                        source_context = context_name.replace("urn:semantic-model:", "")
                    elif context_name.startswith("urn:schema:"):
                        source_context = context_name.replace("urn:schema:", "")
                    elif context_name.startswith("urn:glossary:"):
                        source_context = context_name.replace("urn:glossary:", "")
                    elif context_name.startswith("urn:demo"):
                        source_context = "Demo Data"
                    elif context_name.startswith("urn:app-entities"):
                        source_context = "Application Entities"

                    concepts.append(OntologyConcept(
                        iri=concept_iri,
                        label=label,
                        comment=comment,
                        concept_type=concept_type,
                        source_context=source_context,
                        parent_concepts=parent_concepts
                    ))
            except Exception as e:
                logger.warning(f"Failed to query concepts in context {context_name}: {e}")

        # Second pass: populate child_concepts using O(n) dictionary lookup
        concept_map = {concept.iri: concept for concept in concepts}
        for concept in concepts:
            # For each parent of this concept, add this concept as a child
            for parent_iri in concept.parent_concepts:
                if parent_iri in concept_map:
                    parent_concept = concept_map[parent_iri]
                    if concept.iri not in parent_concept.child_concepts:
                        parent_concept.child_concepts.append(concept.iri)

        return concepts

    def get_concepts_by_taxonomy(self, taxonomy_name: str = None) -> List[OntologyConcept]:
        """Get concepts, optionally filtered by taxonomy"""
        # Check cache first
        cache_key = f"concepts_by_taxonomy:{taxonomy_name or 'all'}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # Compute concepts
        concepts = self._compute_all_concepts(taxonomy_name)

        # Cache for 5 minutes
        self._set_cached(cache_key, concepts, ttl_seconds=300)
        return concepts
    
    def get_concept_details(self, concept_iri: str) -> Optional[OntologyConcept]:
        """Get detailed information about a specific concept"""
        concept = None
        
        # Search all contexts for this concept
        for context in self._graph.contexts():
            if not hasattr(context, 'identifier'):
                continue
            context_id = context.identifier
            context_name = str(context_id)
            
            # Check if concept exists in this context
            concept_uri = URIRef(concept_iri)
            if (concept_uri, None, None) not in context:
                continue
            
            # Get basic info
            labels = list(context.objects(concept_uri, RDFS.label))
            labels.extend(list(context.objects(concept_uri, SKOS.prefLabel)))
            label = str(labels[0]) if labels else None
            
            comments = list(context.objects(concept_uri, RDFS.comment))  
            comments.extend(list(context.objects(concept_uri, SKOS.definition)))
            comment = str(comments[0]) if comments else None
            
            # Determine type
            concept_type = "individual"  # default
            if (concept_uri, RDF.type, RDFS.Class) in context:
                concept_type = "class"
            elif (concept_uri, RDF.type, SKOS.Concept) in context:
                concept_type = "concept"
            
            # Get parent concepts
            parent_concepts = []
            # Handle rdfs:subClassOf relationships (class-to-class)
            for parent in context.objects(concept_uri, RDFS.subClassOf):
                parent_concepts.append(str(parent))
            # Handle SKOS broader relationships
            for parent in context.objects(concept_uri, SKOS.broader):
                parent_concepts.append(str(parent))
            # Handle rdf:type relationships (instance-to-class)
            for parent_type in context.objects(concept_uri, RDF.type):
                # Only include custom types, not basic RDF/RDFS/SKOS types
                parent_type_str = str(parent_type)
                if not any(parent_type_str.startswith(prefix) for prefix in [
                    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
                    "http://www.w3.org/2000/01/rdf-schema#", 
                    "http://www.w3.org/2004/02/skos/core#"
                ]):
                    parent_concepts.append(parent_type_str)
            
            # Get child concepts
            child_concepts = []
            # Handle rdfs:subClassOf relationships (find classes that are subclasses of this one)
            for child in context.subjects(RDFS.subClassOf, concept_uri):
                child_concepts.append(str(child))
            # Handle SKOS narrower relationships
            for child in context.subjects(SKOS.broader, concept_uri):
                child_concepts.append(str(child))
            # Handle rdf:type relationships (find instances of this class)
            for child in context.subjects(RDF.type, concept_uri):
                child_concepts.append(str(child))
            
            # Extract source context
            source_context = None
            if context_name.startswith("urn:taxonomy:"):
                source_context = context_name.replace("urn:taxonomy:", "")
            elif context_name.startswith("urn:semantic-model:"):
                source_context = context_name.replace("urn:semantic-model:", "")
            elif context_name.startswith("urn:schema:"):
                source_context = context_name.replace("urn:schema:", "")
            elif context_name.startswith("urn:glossary:"):
                source_context = context_name.replace("urn:glossary:", "")
            elif context_name.startswith("urn:demo"):
                source_context = "Demo Data"
            elif context_name.startswith("urn:app-entities"):
                source_context = "Application Entities"
            
            concept = OntologyConcept(
                iri=concept_iri,
                label=label,
                comment=comment,
                concept_type=concept_type,
                source_context=source_context,
                parent_concepts=parent_concepts,
                child_concepts=child_concepts
            )
            break  # Found in first matching context
        
        return concept
    
    def get_concept_hierarchy(self, concept_iri: str) -> Optional[ConceptHierarchy]:
        """Get hierarchical relationships for a concept"""
        concept = self.get_concept_details(concept_iri)
        if not concept:
            return None
        
        # Get ancestors (recursive parent lookup)
        ancestors = []
        visited = set()
        
        def get_ancestors_recursive(iri: str):
            if iri in visited:
                return
            visited.add(iri)
            
            parent_concept = self.get_concept_details(iri)
            if not parent_concept:
                return
                
            for parent_iri in parent_concept.parent_concepts:
                parent = self.get_concept_details(parent_iri)
                if parent and parent not in ancestors:
                    ancestors.append(parent)
                    get_ancestors_recursive(parent_iri)
        
        for parent_iri in concept.parent_concepts:
            get_ancestors_recursive(parent_iri)
        
        # Get descendants (recursive child lookup)
        descendants = []
        visited = set()
        
        def get_descendants_recursive(iri: str):
            if iri in visited:
                return
            visited.add(iri)
            
            child_concept = self.get_concept_details(iri)
            if not child_concept:
                return
                
            for child_iri in child_concept.child_concepts:
                child = self.get_concept_details(child_iri)
                if child and child not in descendants:
                    descendants.append(child)
                    get_descendants_recursive(child_iri)
        
        for child_iri in concept.child_concepts:
            get_descendants_recursive(child_iri)
        
        # Get siblings (concepts that share the same parents)
        siblings = []
        if concept.parent_concepts:
            for parent_iri in concept.parent_concepts:
                parent = self.get_concept_details(parent_iri)
                if parent:
                    for sibling_iri in parent.child_concepts:
                        if sibling_iri != concept_iri:
                            sibling = self.get_concept_details(sibling_iri)
                            if sibling and sibling not in siblings:
                                siblings.append(sibling)
        
        return ConceptHierarchy(
            concept=concept,
            ancestors=ancestors,
            descendants=descendants,
            siblings=siblings
        )
    
    def search_ontology_concepts(self, query: str, taxonomy_name: str = None, limit: int = 50) -> List[ConceptSearchResult]:
        """Search for concepts by text query"""
        results = []
        
        # Get concepts to search through
        concepts = self.get_concepts_by_taxonomy(taxonomy_name)
        
        query_lower = query.lower()
        
        for concept in concepts:
            score = 0.0
            match_type = None
            
            # Check label match
            if concept.label and query_lower in concept.label.lower():
                score += 10.0
                match_type = 'label'
                # Exact match gets higher score
                if concept.label.lower() == query_lower:
                    score += 20.0
            
            # Check comment/description match
            if concept.comment and query_lower in concept.comment.lower():
                score += 5.0
                if not match_type:
                    match_type = 'comment'
            
            # Check IRI match
            if query_lower in concept.iri.lower():
                score += 3.0
                if not match_type:
                    match_type = 'iri'
            
            if score > 0:
                results.append(ConceptSearchResult(
                    concept=concept,
                    relevance_score=score,
                    match_type=match_type or 'iri'
                ))
        
        # Sort by relevance score (descending)
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        
        return results[:limit]
    
    def get_taxonomy_stats(self) -> TaxonomyStats:
        """Get statistics about loaded taxonomies"""
        # Check persistent cache first
        cache_file = self._data_dir / "cache" / "stats.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                    return TaxonomyStats(**data)
            except Exception as e:
                logger.warning(f"Failed to load stats from persistent cache: {e}")

        # Fallback to live computation
        logger.warning("Persistent cache not found for stats, computing live")
        taxonomies = self.get_taxonomies()
        all_concepts = self.get_concepts_by_taxonomy()
        stats = self._compute_stats(all_concepts, taxonomies)
        return stats

    def get_grouped_concepts(self) -> Dict[str, List[OntologyConcept]]:
        """Return all concepts grouped by their source context name.

        Group key is derived from OntologyConcept.source_context, or 'Unassigned' when missing.
        Concepts in each group are sorted by label (fallback to IRI).
        """
        # Check persistent cache first
        cache_file = self._data_dir / "cache" / "concepts_all.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                    concepts = [OntologyConcept(**item) for item in data]
            except Exception as e:
                logger.warning(f"Failed to load concepts from persistent cache: {e}")
                concepts = self.get_concepts_by_taxonomy()
        else:
            # Fallback to live computation
            logger.warning("Persistent cache not found for concepts, computing live")
            concepts = self.get_concepts_by_taxonomy()

        # Group concepts by source_context
        grouped: Dict[str, List[OntologyConcept]] = {}
        for concept in concepts:
            source = concept.source_context or "Unassigned"
            if source not in grouped:
                grouped[source] = []
            grouped[source].append(concept)

        # Sort concepts within each group
        for source in grouped:
            grouped[source].sort(key=lambda c: (c.label or c.iri))

        return grouped

