"""Model Context Protocol (MCP) integration.

External MCP servers are plugged in here: ``manager`` owns the connections and
tool discovery, and ``tool`` adapts each discovered MCP tool to Odin's
``BaseTool`` contract so it flows through the normal security gate.
"""
