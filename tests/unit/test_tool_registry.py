"""Tool registry: registration, lookup, subsetting."""

from aegis.execute.tool_registry import ToolRegistry, default_registry, tool


@tool(
    name="add",
    description="Add two numbers",
    parameters={
        "type": "object",
        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        "required": ["a", "b"],
    },
)
def _add(a: float, b: float) -> float:
    return a + b


def test_register_and_get():
    reg = ToolRegistry()
    reg.register(_add)
    spec = reg.get("add")
    assert spec is not None
    assert spec.fn(2, 3) == 5


def test_subset_filters():
    reg = ToolRegistry()
    reg.register(_add)
    sub = reg.subset(["add", "nonexistent"])
    assert sub.names() == ["add"]


def test_default_registry_has_builtins():
    reg = default_registry()
    for name in (
        "fetch_url",
        "web_search",
        "read_file",
        "write_file",
        "list_dir",
        "run_python_snippet",
    ):
        assert name in reg.names(), f"Missing built-in tool: {name}"
