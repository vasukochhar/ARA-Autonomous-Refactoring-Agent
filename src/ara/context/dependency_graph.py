"""
Dependency Graph Builder - Analyze and build dependency graphs.

Uses AST analysis to identify imports, function calls, and class hierarchies.
"""

from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import ast

import structlog

logger = structlog.get_logger()


@dataclass
class ModuleInfo:
    """Information about a Python module."""
    
    filepath: str
    module_name: str
    imports: List[str] = field(default_factory=list)  # Modules this imports
    imported_from: List[str] = field(default_factory=list)  # Symbols imported
    defines_functions: List[str] = field(default_factory=list)
    defines_classes: List[str] = field(default_factory=list)
    calls: List[str] = field(default_factory=list)  # External function calls


@dataclass
class DependencyGraph:
    """A graph of module dependencies."""
    
    modules: Dict[str, ModuleInfo] = field(default_factory=dict)
    edges: List[Tuple[str, str]] = field(default_factory=list)  # (from, to)
    
    def add_module(self, info: ModuleInfo):
        """Add a module to the graph."""
        self.modules[info.filepath] = info
    
    def add_edge(self, from_module: str, to_module: str):
        """Add a dependency edge."""
        self.edges.append((from_module, to_module))
    
    def get_dependents(self, module_path: str) -> List[str]:
        """Get modules that depend on the given module."""
        return [from_mod for from_mod, to_mod in self.edges if to_mod == module_path]
    
    def get_dependencies(self, module_path: str) -> List[str]:
        """Get modules that the given module depends on."""
        return [to_mod for from_mod, to_mod in self.edges if from_mod == module_path]
    
    def topological_sort(self) -> List[str]:
        """
        Return modules in topological order (dependencies first).
        
        Useful for determining the order to process files.
        """
        # Build adjacency list
        adj: Dict[str, List[str]] = {m: [] for m in self.modules}
        in_degree: Dict[str, int] = {m: 0 for m in self.modules}
        
        for from_mod, to_mod in self.edges:
            if from_mod in adj and to_mod in self.modules:
                adj[from_mod].append(to_mod)
                in_degree[to_mod] += 1
        
        # Kahn's algorithm
        queue = [m for m, d in in_degree.items() if d == 0]
        result = []
        
        while queue:
            node = queue.pop(0)
            result.append(node)
            
            for neighbor in adj.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # If we couldn't sort all nodes, there's a cycle
        if len(result) != len(self.modules):
            logger.warning("circular_dependency_detected")
            # Return remaining nodes at the end
            remaining = [m for m in self.modules if m not in result]
            result.extend(remaining)
        
        return result


class DependencyAnalyzer(ast.NodeVisitor):
    """AST visitor to extract dependency information from Python code."""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.module_name = Path(filepath).stem
        self.imports: List[str] = []
        self.imported_from: List[str] = []
        self.functions: List[str] = []
        self.classes: List[str] = []
        self.calls: List[str] = []
    
    def visit_Import(self, node: ast.Import):
        """Track import statements."""
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Track from ... import statements."""
        if node.module:
            self.imports.append(node.module)
            for alias in node.names:
                self.imported_from.append(f"{node.module}.{alias.name}")
        self.generic_visit(node)
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Track function definitions."""
        self.functions.append(node.name)
        self.generic_visit(node)
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Track async function definitions."""
        self.functions.append(node.name)
        self.generic_visit(node)
    
    def visit_ClassDef(self, node: ast.ClassDef):
        """Track class definitions."""
        self.classes.append(node.name)
        self.generic_visit(node)
    
    def visit_Call(self, node: ast.Call):
        """Track function calls."""
        call_name = self._get_call_name(node.func)
        if call_name:
            self.calls.append(call_name)
        self.generic_visit(node)
    
    def _get_call_name(self, node: ast.expr) -> Optional[str]:
        """Extract the name of a function being called."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            value_name = self._get_call_name(node.value)
            if value_name:
                return f"{value_name}.{node.attr}"
            return node.attr
        return None
    
    def get_module_info(self) -> ModuleInfo:
        """Get the extracted module information."""
        return ModuleInfo(
            filepath=self.filepath,
            module_name=self.module_name,
            imports=self.imports,
            imported_from=self.imported_from,
            defines_functions=self.functions,
            defines_classes=self.classes,
            calls=self.calls,
        )


def analyze_file(filepath: str, source_code: str) -> Optional[ModuleInfo]:
    """
    Analyze a single Python file for dependencies.
    
    Args:
        filepath: Path to the file
        source_code: Content of the file
    
    Returns:
        ModuleInfo with extracted dependencies, or None on error
    """
    try:
        tree = ast.parse(source_code)
        analyzer = DependencyAnalyzer(filepath)
        analyzer.visit(tree)
        return analyzer.get_module_info()
    except SyntaxError as e:
        logger.warning("syntax_error_in_file", filepath=filepath, error=str(e))
        return None
    except Exception as e:
        logger.error("analysis_error", filepath=filepath, error=str(e))
        return None


def build_dependency_graph(
    files: Dict[str, str],
    base_path: Optional[str] = None,
) -> DependencyGraph:
    """
    Build a dependency graph from a collection of files.
    
    Args:
        files: Dict mapping filepath to source code
        base_path: Optional base path for resolving relative imports
    
    Returns:
        DependencyGraph with all modules and their relationships
    """
    graph = DependencyGraph()
    
    # First pass: analyze all files
    for filepath, source_code in files.items():
        info = analyze_file(filepath, source_code)
        if info:
            graph.add_module(info)
    
    # Second pass: build edges based on imports
    module_names = {
        Path(fp).stem: fp for fp in graph.modules.keys()
    }
    
    for filepath, info in graph.modules.items():
        for imported in info.imports:
            # Check if this import corresponds to one of our files
            module_file = module_names.get(imported.split(".")[-1])
            if module_file and module_file != filepath:
                graph.add_edge(filepath, module_file)
    
    logger.info(
        "dependency_graph_built",
        modules=len(graph.modules),
        edges=len(graph.edges),
    )
    
    return graph


def find_affected_files(
    graph: DependencyGraph,
    changed_file: str,
    symbol: Optional[str] = None,
) -> List[str]:
    """
    Find all files that might be affected by a change.
    
    Args:
        graph: The dependency graph
        changed_file: File that was changed
        symbol: Optional specific symbol that was changed
    
    Returns:
        List of filepaths that might need updating
    """
    affected = set()
    to_process = [changed_file]
    
    while to_process:
        current = to_process.pop(0)
        if current in affected:
            continue
        
        affected.add(current)
        
        # Get all files that depend on this one
        dependents = graph.get_dependents(current)
        to_process.extend(d for d in dependents if d not in affected)
    
    # Remove the original file from affected
    affected.discard(changed_file)
    
    return list(affected)


@dataclass
class SymbolDefinition:
    """A symbol definition (function, class, variable)."""
    name: str
    filepath: str
    line_number: int
    symbol_type: str  # 'function', 'class', 'variable', 'import'
    scope: Optional[str] = None  # Parent class/function if nested


@dataclass
class SymbolReference:
    """A reference to a symbol."""
    name: str
    filepath: str
    line_number: int
    context: str  # 'call', 'import', 'attribute', 'annotation'


class SymbolResolver:
    """
    Resolves symbols across multiple files.
    
    Tracks where symbols are defined and where they're used,
    enabling accurate cross-file refactoring.
    """
    
    def __init__(self):
        self.definitions: Dict[str, List[SymbolDefinition]] = {}  # symbol -> definitions
        self.references: Dict[str, List[SymbolReference]] = {}  # symbol -> references
        self.file_symbols: Dict[str, Set[str]] = {}  # filepath -> symbols defined
    
    def add_definition(self, symbol: SymbolDefinition):
        """Add a symbol definition."""
        if symbol.name not in self.definitions:
            self.definitions[symbol.name] = []
        self.definitions[symbol.name].append(symbol)
        
        if symbol.filepath not in self.file_symbols:
            self.file_symbols[symbol.filepath] = set()
        self.file_symbols[symbol.filepath].add(symbol.name)
    
    def add_reference(self, ref: SymbolReference):
        """Add a symbol reference."""
        if ref.name not in self.references:
            self.references[ref.name] = []
        self.references[ref.name].append(ref)
    
    def find_definition(self, symbol_name: str, from_file: Optional[str] = None) -> Optional[SymbolDefinition]:
        """
        Find the definition of a symbol.
        
        Args:
            symbol_name: Name of the symbol
            from_file: File where the reference is (for scoping)
        
        Returns:
            The most likely definition or None
        """
        defs = self.definitions.get(symbol_name, [])
        if not defs:
            return None
        
        # Prefer definitions in the same file
        if from_file:
            same_file = [d for d in defs if d.filepath == from_file]
            if same_file:
                return same_file[0]
        
        return defs[0]
    
    def find_references(self, symbol_name: str) -> List[SymbolReference]:
        """Find all references to a symbol."""
        return self.references.get(symbol_name, [])
    
    def get_files_using_symbol(self, symbol_name: str) -> Set[str]:
        """Get all files that reference a symbol."""
        refs = self.find_references(symbol_name)
        return {r.filepath for r in refs}
    
    def rename_symbol_impact(self, old_name: str) -> Dict[str, List[int]]:
        """
        Determine the impact of renaming a symbol.
        
        Returns:
            Dict mapping filepath to list of line numbers that need updating
        """
        impact: Dict[str, List[int]] = {}
        
        # Add definition locations
        for defn in self.definitions.get(old_name, []):
            if defn.filepath not in impact:
                impact[defn.filepath] = []
            impact[defn.filepath].append(defn.line_number)
        
        # Add reference locations
        for ref in self.references.get(old_name, []):
            if ref.filepath not in impact:
                impact[ref.filepath] = []
            impact[ref.filepath].append(ref.line_number)
        
        # Sort line numbers
        for filepath in impact:
            impact[filepath] = sorted(set(impact[filepath]))
        
        return impact


class SymbolExtractor(ast.NodeVisitor):
    """Extract symbol definitions and references from AST."""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.definitions: List[SymbolDefinition] = []
        self.references: List[SymbolReference] = []
        self.current_scope: Optional[str] = None
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.definitions.append(SymbolDefinition(
            name=node.name,
            filepath=self.filepath,
            line_number=node.lineno,
            symbol_type='function',
            scope=self.current_scope,
        ))
        old_scope = self.current_scope
        self.current_scope = node.name
        self.generic_visit(node)
        self.current_scope = old_scope
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.definitions.append(SymbolDefinition(
            name=node.name,
            filepath=self.filepath,
            line_number=node.lineno,
            symbol_type='function',
            scope=self.current_scope,
        ))
        old_scope = self.current_scope
        self.current_scope = node.name
        self.generic_visit(node)
        self.current_scope = old_scope
    
    def visit_ClassDef(self, node: ast.ClassDef):
        self.definitions.append(SymbolDefinition(
            name=node.name,
            filepath=self.filepath,
            line_number=node.lineno,
            symbol_type='class',
            scope=self.current_scope,
        ))
        old_scope = self.current_scope
        self.current_scope = node.name
        self.generic_visit(node)
        self.current_scope = old_scope
    
    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            self.references.append(SymbolReference(
                name=node.id,
                filepath=self.filepath,
                line_number=node.lineno,
                context='reference',
            ))
        self.generic_visit(node)
    
    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            self.references.append(SymbolReference(
                name=node.func.id,
                filepath=self.filepath,
                line_number=node.lineno,
                context='call',
            ))
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
        for alias in node.names:
            self.definitions.append(SymbolDefinition(
                name=alias.asname or alias.name,
                filepath=self.filepath,
                line_number=node.lineno,
                symbol_type='import',
            ))
        self.generic_visit(node)


def build_symbol_table(files: Dict[str, str]) -> SymbolResolver:
    """
    Build a complete symbol table from multiple files.
    
    Args:
        files: Dict mapping filepath to source code
    
    Returns:
        SymbolResolver with all definitions and references
    """
    resolver = SymbolResolver()
    
    for filepath, source_code in files.items():
        try:
            tree = ast.parse(source_code)
            extractor = SymbolExtractor(filepath)
            extractor.visit(tree)
            
            for defn in extractor.definitions:
                resolver.add_definition(defn)
            for ref in extractor.references:
                resolver.add_reference(ref)
                
        except SyntaxError as e:
            logger.warning("symbol_extraction_syntax_error", filepath=filepath, error=str(e))
        except Exception as e:
            logger.error("symbol_extraction_error", filepath=filepath, error=str(e))
    
    logger.info(
        "symbol_table_built",
        definitions=sum(len(v) for v in resolver.definitions.values()),
        references=sum(len(v) for v in resolver.references.values()),
        files=len(files),
    )
    
    return resolver


def get_refactoring_order(
    graph: DependencyGraph,
    target_files: List[str],
) -> List[str]:
    """
    Determine the order to process files for refactoring.
    
    Processes leaf nodes (no dependencies) first, then works up.
    
    Args:
        graph: The dependency graph
        target_files: Files to be refactored
    
    Returns:
        Ordered list of files to process
    """
    # Get topological order
    all_ordered = graph.topological_sort()
    
    # Filter to only target files, maintaining order
    ordered = [f for f in all_ordered if f in target_files]
    
    # Add any target files not in graph
    for f in target_files:
        if f not in ordered:
            ordered.append(f)
    
    return ordered

