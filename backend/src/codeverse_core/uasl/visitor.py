"""Generic visitor over UASL nodes.

Codegen modules subclass this. Dispatch is by node class name: ``visit(node)``
routes to ``visit_FunctionDef``, ``visit_If``, ... Unhandled node types hit
``generic_visit`` which raises — a new UASL node type therefore fails loudly
in every codegen module until explicitly supported.
"""

from __future__ import annotations

from typing import Any

from codeverse_core.uasl import nodes


class UASLVisitor:
    def visit(self, node: nodes.Node) -> Any:
        method = getattr(self, f"visit_{type(node).__name__}", None)
        if method is None:
            return self.generic_visit(node)
        return method(node)

    def generic_visit(self, node: nodes.Node) -> Any:
        raise NotImplementedError(
            f"{type(self).__name__} does not handle UASL node {type(node).__name__}"
        )
