import anyio
import json
from mcp import ClientSession
from mcp.client.sse import sse_client

async def main():
    print("Connecting to Figma MCP Server at https://mcp.figma.com/mcp...")
    try:
        async with sse_client("https://mcp.figma.com/mcp") as (read_stream, write_stream):
            print("SSE connection established. Creating ClientSession...")
            async with ClientSession(read_stream, write_stream) as session:
                print("Initializing session...")
                await session.initialize()
                print("Session initialized successfully! Listing tools...")
                
                tools_result = await session.list_tools()
                print("\nTools found:")
                tools = tools_result.tools if hasattr(tools_result, 'tools') else tools_result
                for tool in tools:
                    print(f"- {tool.name}: {tool.description}")
                    if tool.inputSchema:
                        print("  Schema:", json.dumps(tool.inputSchema, indent=2))
                
                print("\nListing resources...")
                try:
                    resources_result = await session.list_resources()
                    resources = resources_result.resources if hasattr(resources_result, 'resources') else resources_result
                    print(f"Resources found: {len(resources)}")
                    for res in resources:
                        print(f"- {res.name} ({res.uri}): {res.description}")
                except Exception as e:
                    print(f"Failed to list resources: {e}")
                    
    except Exception as e:
        import traceback
        print(f"An error occurred: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    anyio.run(main)
