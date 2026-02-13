"""
Unity Catalog Data Connector for ML Training Data

Fetches data from Unity Catalog tables and volumes for QA pair generation.
Follows Ontos's workspace client and statement execution patterns.
"""

import base64
import json
import logging
import random
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

from src.common.config import Settings
from src.common.unity_catalog_utils import sanitize_uc_identifier

logger = logging.getLogger(__name__)


class SamplingStrategy(str, Enum):
    """Sampling strategies for fetching data"""
    ALL = "all"
    RANDOM = "random"
    STRATIFIED = "stratified"
    FIRST_N = "first_n"


@dataclass
class DataFetchConfig:
    """Configuration for fetching data from Unity Catalog"""
    # Source location
    catalog: str
    schema: str
    table: Optional[str] = None
    volume_path: Optional[str] = None  # For files in volumes

    # Column selection
    text_columns: List[str] = None
    image_columns: List[str] = None
    metadata_columns: List[str] = None
    id_column: Optional[str] = None

    # Sampling
    sampling_strategy: SamplingStrategy = SamplingStrategy.ALL
    sample_size: Optional[int] = None
    sample_filter: Optional[str] = None  # WHERE clause
    stratify_column: Optional[str] = None

    def __post_init__(self):
        self.text_columns = self.text_columns or []
        self.image_columns = self.image_columns or []
        self.metadata_columns = self.metadata_columns or []


@dataclass
class DataFetchResult:
    """Result of fetching data"""
    items: List[Dict[str, Any]]
    total_count: int
    sampled_count: int
    columns: List[str]
    source: str  # catalog.schema.table or volume path


class UnityCatalogDataConnector:
    """
    Connector for fetching data from Unity Catalog for ML training.

    Supports:
    - Unity Catalog tables (via Statement Execution API)
    - Unity Catalog volumes (for file-based data)
    - Multiple sampling strategies
    - Multimodal data (text + images)
    """

    def __init__(
        self,
        workspace_client: WorkspaceClient,
        settings: Settings,
        warehouse_id: Optional[str] = None
    ):
        self._ws = workspace_client
        self._settings = settings
        self._warehouse_id = warehouse_id or settings.DATABRICKS_WAREHOUSE_ID

    def fetch_table_data(
        self,
        config: DataFetchConfig,
        timeout_seconds: int = 120
    ) -> DataFetchResult:
        """
        Fetch data from a Unity Catalog table.

        Args:
            config: Data fetch configuration
            timeout_seconds: Query timeout

        Returns:
            DataFetchResult with items and metadata
        """
        if not config.table:
            raise ValueError("Table name required for table data fetch")

        # Sanitize identifiers
        catalog = sanitize_uc_identifier(config.catalog)
        schema = sanitize_uc_identifier(config.schema)
        table = sanitize_uc_identifier(config.table)
        full_table_name = f"`{catalog}`.`{schema}`.`{table}`"

        # Build column list
        columns = self._build_column_list(config)
        if not columns:
            columns = ["*"]

        # Build query
        query = self._build_query(
            full_table_name=full_table_name,
            columns=columns,
            config=config
        )

        logger.info(f"Executing query: {query[:200]}...")

        # Execute query
        items = self._execute_query(query, timeout_seconds)

        # Get total count if sampling
        total_count = len(items)
        if config.sample_size and config.sampling_strategy != SamplingStrategy.ALL:
            total_count = self._get_total_count(full_table_name, config.sample_filter)

        return DataFetchResult(
            items=items,
            total_count=total_count,
            sampled_count=len(items),
            columns=columns if columns != ["*"] else self._get_column_names(items),
            source=f"{catalog}.{schema}.{table}"
        )

    def fetch_volume_data(
        self,
        config: DataFetchConfig,
        file_extensions: Optional[List[str]] = None
    ) -> DataFetchResult:
        """
        Fetch data from Unity Catalog volume (file-based).

        Args:
            config: Data fetch configuration with volume_path
            file_extensions: Filter by file extensions (e.g., [".json", ".txt"])

        Returns:
            DataFetchResult with items (file contents/paths) and metadata
        """
        if not config.volume_path:
            raise ValueError("Volume path required for volume data fetch")

        # Parse volume path: /Volumes/catalog/schema/volume_name/path
        volume_parts = self._parse_volume_path(config.volume_path)
        if not volume_parts:
            raise ValueError(f"Invalid volume path: {config.volume_path}")

        catalog, schema, volume_name, subpath = volume_parts

        # List files in volume
        files = self._list_volume_files(
            catalog=catalog,
            schema=schema,
            volume_name=volume_name,
            subpath=subpath,
            extensions=file_extensions
        )

        # Apply sampling
        if config.sampling_strategy == SamplingStrategy.RANDOM and config.sample_size:
            if len(files) > config.sample_size:
                files = random.sample(files, config.sample_size)
        elif config.sampling_strategy == SamplingStrategy.FIRST_N and config.sample_size:
            files = files[:config.sample_size]

        # Build items from files
        items = []
        for file_info in files:
            item = {
                "file_path": file_info["path"],
                "file_name": file_info["name"],
                "file_size": file_info.get("size", 0),
                "modification_time": file_info.get("modification_time")
            }

            # Optionally read file content for small text files
            if file_info.get("size", 0) < 1_000_000:  # < 1MB
                content = self._read_volume_file(file_info["path"])
                if content:
                    item["content"] = content

            items.append(item)

        return DataFetchResult(
            items=items,
            total_count=len(files),
            sampled_count=len(items),
            columns=["file_path", "file_name", "file_size", "content"],
            source=config.volume_path
        )

    def preview_data(
        self,
        config: DataFetchConfig,
        limit: int = 5
    ) -> DataFetchResult:
        """
        Preview a small sample of data (for template testing).

        Args:
            config: Data fetch configuration
            limit: Number of rows to preview

        Returns:
            DataFetchResult with preview items
        """
        preview_config = DataFetchConfig(
            catalog=config.catalog,
            schema=config.schema,
            table=config.table,
            volume_path=config.volume_path,
            text_columns=config.text_columns,
            image_columns=config.image_columns,
            metadata_columns=config.metadata_columns,
            id_column=config.id_column,
            sampling_strategy=SamplingStrategy.FIRST_N,
            sample_size=limit
        )

        if config.table:
            return self.fetch_table_data(preview_config)
        elif config.volume_path:
            return self.fetch_volume_data(preview_config)
        else:
            raise ValueError("Either table or volume_path required")

    def validate_source(
        self,
        config: DataFetchConfig
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate that the source exists and is accessible.

        Returns:
            (is_valid, error_message)
        """
        try:
            if config.table:
                # Check table exists
                catalog = sanitize_uc_identifier(config.catalog)
                schema = sanitize_uc_identifier(config.schema)
                table = sanitize_uc_identifier(config.table)

                table_info = self._ws.tables.get(f"{catalog}.{schema}.{table}")
                if not table_info:
                    return False, f"Table {catalog}.{schema}.{table} not found"

                # Validate columns exist
                table_columns = {col.name for col in (table_info.columns or [])}
                all_config_columns = (
                    config.text_columns +
                    config.image_columns +
                    config.metadata_columns +
                    ([config.id_column] if config.id_column else [])
                )

                missing = [c for c in all_config_columns if c and c not in table_columns]
                if missing:
                    return False, f"Columns not found in table: {missing}"

                return True, None

            elif config.volume_path:
                # Check volume exists
                volume_parts = self._parse_volume_path(config.volume_path)
                if not volume_parts:
                    return False, f"Invalid volume path: {config.volume_path}"

                catalog, schema, volume_name, _ = volume_parts

                try:
                    self._ws.volumes.read(f"{catalog}.{schema}.{volume_name}")
                    return True, None
                except Exception as e:
                    return False, f"Volume not accessible: {e}"

            else:
                return False, "Either table or volume_path required"

        except Exception as e:
            return False, str(e)

    def get_table_schema(
        self,
        catalog: str,
        schema: str,
        table: str
    ) -> List[Dict[str, Any]]:
        """Get schema information for a table"""
        catalog = sanitize_uc_identifier(catalog)
        schema = sanitize_uc_identifier(schema)
        table = sanitize_uc_identifier(table)

        table_info = self._ws.tables.get(f"{catalog}.{schema}.{table}")

        return [
            {
                "name": col.name,
                "type": col.type_text,
                "nullable": col.nullable,
                "comment": col.comment
            }
            for col in (table_info.columns or [])
        ]

    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================

    def _build_column_list(self, config: DataFetchConfig) -> List[str]:
        """Build list of columns to select"""
        columns = []

        if config.id_column:
            columns.append(config.id_column)

        columns.extend(config.text_columns)
        columns.extend(config.image_columns)
        columns.extend(config.metadata_columns)

        # Deduplicate while preserving order
        seen = set()
        unique_columns = []
        for col in columns:
            if col and col not in seen:
                seen.add(col)
                unique_columns.append(col)

        return unique_columns

    def _build_query(
        self,
        full_table_name: str,
        columns: List[str],
        config: DataFetchConfig
    ) -> str:
        """Build SQL query with sampling"""
        # Sanitize column names
        safe_columns = [f"`{sanitize_uc_identifier(c)}`" for c in columns] if columns != ["*"] else ["*"]
        column_str = ", ".join(safe_columns)

        query = f"SELECT {column_str} FROM {full_table_name}"

        # Add WHERE clause
        if config.sample_filter:
            # Basic SQL injection prevention - only allow safe patterns
            if self._is_safe_filter(config.sample_filter):
                query += f" WHERE {config.sample_filter}"
            else:
                logger.warning(f"Unsafe filter rejected: {config.sample_filter}")

        # Add sampling
        if config.sampling_strategy == SamplingStrategy.RANDOM and config.sample_size:
            # Use TABLESAMPLE for efficient random sampling
            query = f"SELECT * FROM ({query}) TABLESAMPLE ({config.sample_size} ROWS)"

        elif config.sampling_strategy == SamplingStrategy.STRATIFIED and config.stratify_column:
            # Stratified sampling using window functions
            stratify_col = sanitize_uc_identifier(config.stratify_column)
            samples_per_stratum = config.sample_size // 10 if config.sample_size else 100

            query = f"""
            WITH ranked AS (
                SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY `{stratify_col}` ORDER BY RAND()) as _rn
                FROM ({query}) t
            )
            SELECT * EXCEPT(_rn)
            FROM ranked
            WHERE _rn <= {samples_per_stratum}
            """

        elif config.sampling_strategy == SamplingStrategy.FIRST_N and config.sample_size:
            query += f" LIMIT {config.sample_size}"

        elif config.sampling_strategy == SamplingStrategy.ALL and config.sample_size:
            # ALL with sample_size acts as a limit
            query += f" LIMIT {config.sample_size}"

        return query

    def _is_safe_filter(self, filter_str: str) -> bool:
        """
        Basic safety check for filter expressions.

        Rejects obviously dangerous patterns.
        """
        dangerous_patterns = [
            r';\s*',  # Statement terminator
            r'--',    # SQL comment
            r'/\*',   # Block comment
            r'\bDROP\b',
            r'\bDELETE\b',
            r'\bTRUNCATE\b',
            r'\bINSERT\b',
            r'\bUPDATE\b',
            r'\bCREATE\b',
            r'\bALTER\b',
            r'\bEXEC\b',
            r'\bUNION\b',
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, filter_str, re.IGNORECASE):
                return False

        return True

    def _execute_query(
        self,
        query: str,
        timeout_seconds: int = 120
    ) -> List[Dict[str, Any]]:
        """Execute SQL query and return results as list of dicts"""
        if not self._warehouse_id:
            raise ValueError("DATABRICKS_WAREHOUSE_ID required for SQL queries")

        try:
            response = self._ws.statement_execution.execute_statement(
                warehouse_id=self._warehouse_id,
                statement=query,
                wait_timeout=f"{timeout_seconds}s"
            )

            # Check status
            if response.status.state == StatementState.FAILED:
                error = response.status.error
                raise RuntimeError(f"Query failed: {error.message if error else 'Unknown error'}")

            if response.status.state == StatementState.CANCELED:
                raise RuntimeError("Query was canceled")

            if response.status.state != StatementState.SUCCEEDED:
                raise RuntimeError(f"Query in unexpected state: {response.status.state}")

            # Parse results
            if not response.result or not response.result.data_array:
                return []

            # Get column names from schema
            columns = [col.name for col in response.manifest.schema.columns]

            # Convert to list of dicts
            items = []
            for row in response.result.data_array:
                item = {}
                for i, col_name in enumerate(columns):
                    value = row[i] if i < len(row) else None
                    item[col_name] = value
                items.append(item)

            return items

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise

    def _get_total_count(
        self,
        full_table_name: str,
        filter_clause: Optional[str] = None
    ) -> int:
        """Get total row count for a table"""
        query = f"SELECT COUNT(*) as cnt FROM {full_table_name}"
        if filter_clause and self._is_safe_filter(filter_clause):
            query += f" WHERE {filter_clause}"

        results = self._execute_query(query, timeout_seconds=30)
        if results:
            return int(results[0].get("cnt", 0))
        return 0

    def _get_column_names(self, items: List[Dict[str, Any]]) -> List[str]:
        """Extract column names from result items"""
        if not items:
            return []
        return list(items[0].keys())

    def _parse_volume_path(
        self,
        volume_path: str
    ) -> Optional[Tuple[str, str, str, str]]:
        """
        Parse volume path into components.

        Format: /Volumes/catalog/schema/volume_name/subpath
        Returns: (catalog, schema, volume_name, subpath)
        """
        # Normalize path
        path = volume_path.strip()
        if path.startswith("/Volumes/"):
            path = path[9:]  # Remove "/Volumes/"
        elif path.startswith("dbfs:/Volumes/"):
            path = path[14:]  # Remove "dbfs:/Volumes/"

        parts = path.split("/")
        if len(parts) < 3:
            return None

        catalog = parts[0]
        schema = parts[1]
        volume_name = parts[2]
        subpath = "/".join(parts[3:]) if len(parts) > 3 else ""

        return catalog, schema, volume_name, subpath

    def _list_volume_files(
        self,
        catalog: str,
        schema: str,
        volume_name: str,
        subpath: str = "",
        extensions: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """List files in a volume"""
        volume_path = f"/Volumes/{catalog}/{schema}/{volume_name}"
        if subpath:
            volume_path = f"{volume_path}/{subpath}"

        try:
            files = []
            for item in self._ws.files.list_directory_contents(volume_path):
                if item.is_directory:
                    continue

                # Filter by extension
                if extensions:
                    if not any(item.name.endswith(ext) for ext in extensions):
                        continue

                files.append({
                    "path": item.path,
                    "name": item.name,
                    "size": item.file_size,
                    "modification_time": item.last_modified
                })

            return files

        except Exception as e:
            logger.error(f"Failed to list volume files: {e}")
            raise

    def _read_volume_file(self, file_path: str) -> Optional[str]:
        """Read content of a file from volume"""
        try:
            response = self._ws.files.download(file_path)
            content = response.contents.read()

            # Try to decode as text
            try:
                return content.decode('utf-8')
            except UnicodeDecodeError:
                # Return base64 for binary content
                return f"base64:{base64.b64encode(content).decode('ascii')}"

        except Exception as e:
            logger.warning(f"Failed to read file {file_path}: {e}")
            return None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_connector_from_sheet(
    sheet_db,  # SheetDb instance
    workspace_client: WorkspaceClient,
    settings: Settings
) -> Tuple[UnityCatalogDataConnector, DataFetchConfig]:
    """
    Create a connector and config from a Sheet database model.

    Args:
        sheet_db: SheetDb instance with source configuration
        workspace_client: Databricks workspace client
        settings: Application settings

    Returns:
        (connector, config) tuple ready for data fetching
    """
    connector = UnityCatalogDataConnector(
        workspace_client=workspace_client,
        settings=settings
    )

    # Determine if table or volume
    volume_path = None
    if sheet_db.source_volume:
        # Build volume path
        if sheet_db.source_path:
            volume_path = f"/Volumes/{sheet_db.source_catalog}/{sheet_db.source_schema}/{sheet_db.source_volume}/{sheet_db.source_path}"
        else:
            volume_path = f"/Volumes/{sheet_db.source_catalog}/{sheet_db.source_schema}/{sheet_db.source_volume}"

    config = DataFetchConfig(
        catalog=sheet_db.source_catalog,
        schema=sheet_db.source_schema,
        table=sheet_db.source_table,
        volume_path=volume_path,
        text_columns=sheet_db.text_columns or [],
        image_columns=sheet_db.image_columns or [],
        metadata_columns=sheet_db.metadata_columns or [],
        id_column=sheet_db.id_column,
        sampling_strategy=SamplingStrategy(sheet_db.sampling_strategy.value) if sheet_db.sampling_strategy else SamplingStrategy.ALL,
        sample_size=sheet_db.sample_size,
        sample_filter=sheet_db.sample_filter,
        stratify_column=sheet_db.stratify_column
    )

    return connector, config
