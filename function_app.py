import os
import json
import xmltodict
import logging
from datetime import datetime, timezone
import azure.functions as func
import httpx

# --- Configuration ---
SAP_BASE_URL = os.getenv("SAP_BASE_URL", "http://sbx-s4s-app.northeurope.cloudapp.azure.com:54000")
SAP_BP_SERVICE = f"{SAP_BASE_URL}/sap/opu/odata/sap/API_BUSINESS_PARTNER"
SAP_SO_SERVICE = f"{SAP_BASE_URL}/sap/opu/odata/sap/API_SALES_ORDER_SRV"

# --- BUSINESS PARTNER API Entity Mappings ---
BP_ODATA = {
    "businesspartners": f"{SAP_BP_SERVICE}/A_BusinessPartner",
    "businesspartneraddresses": f"{SAP_BP_SERVICE}/A_BusinessPartnerAddress",
    "businesspartnercontacts": f"{SAP_BP_SERVICE}/A_BusinessPartnerContact",
    "customers": f"{SAP_BP_SERVICE}/A_Customer",
    "suppliers": f"{SAP_BP_SERVICE}/A_Supplier"
}

BP_ODATA_CREATE = {
    "businesspartneraddresses": f"{SAP_BP_SERVICE}/A_BusinessPartnerAddress",
    "businesspartnercontacts": f"{SAP_BP_SERVICE}/A_BusinessPartnerContact"
}

# --- SALES ORDER API Entity Mappings ---
SO_ODATA = {
    "salesorders": f"{SAP_SO_SERVICE}/A_SalesOrder",
    "salesorderitems": f"{SAP_SO_SERVICE}/A_SalesOrderItem",
    "salesorderheaderpartners": f"{SAP_SO_SERVICE}/A_SalesOrderHeaderPartner",
    "salesorderitempartners": f"{SAP_SO_SERVICE}/A_SalesOrderItemPartner",
    "salesorderschedulelines": f"{SAP_SO_SERVICE}/A_SalesOrderScheduleLine",
    "salesordertexts": f"{SAP_SO_SERVICE}/A_SalesOrderText",
    "salesorderitemtexts": f"{SAP_SO_SERVICE}/A_SalesOrderItemText"
}

SO_ODATA_CREATE = {
    "salesorders": f"{SAP_SO_SERVICE}/A_SalesOrder",
    "salesorderitems": f"{SAP_SO_SERVICE}/A_SalesOrderItem",
    "salesorderheaderpartners": f"{SAP_SO_SERVICE}/A_SalesOrderHeaderPartner",
    "salesorderitempartners": f"{SAP_SO_SERVICE}/A_SalesOrderItemPartner",
    "salesorderschedulelines": f"{SAP_SO_SERVICE}/A_SalesOrderScheduleLine",
    "salesordertexts": f"{SAP_SO_SERVICE}/A_SalesOrderText",
    "salesorderitemtexts": f"{SAP_SO_SERVICE}/A_SalesOrderItemText"
}

# --- COMBINED MAPPINGS for MCP Tools ---
ALL_ODATA = {**BP_ODATA, **SO_ODATA}
ALL_ODATA = {k.lower(): v for k, v in ALL_ODATA.items()}

ALL_ODATA_CREATE = {**BP_ODATA_CREATE, **SO_ODATA_CREATE}  
ALL_ODATA_CREATE = {k.lower(): v for k, v in ALL_ODATA_CREATE.items()}

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# --- Helper function for CORS headers ---
def add_cors_headers(response):
    """Add CORS headers to response"""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Ocp-Apim-Subscription-Key"
    return response

# --- MCP Tool Discovery - Combined BP & SO ---
@app.route(route="tools", methods=["GET", "OPTIONS"])
async def tools_discovery(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        response = func.HttpResponse("")
        return add_cors_headers(response)
    
    accept_header = req.headers.get("accept", "")
    
    # For MCP clients requesting JSON tools list
    if req.method == "GET" and "application/json" in accept_header:
        # Check if this is an MCP JSON-RPC request
        body = None
        try:
            body = req.get_json()
        except Exception:
            body = None
            
        # Handle as MCP JSON-RPC tools/list request
        if body and body.get("method") == "tools/list":
            msg_id = body.get("id", 1)
            mcp_response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": [
                        {
                            "name": "query_s4hana",
                            "description": "Query S/4HANA entities (Business Partners: businesspartners, customers, suppliers | Sales Orders: salesorders, salesorderitems, salesorderheaderpartners)",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "entity": {
                                        "type": "string",
                                        "description": "S/4HANA OData entity name",
                                        "enum": list(ALL_ODATA.keys())
                                    },
                                    "query": {
                                        "type": "string",
                                        "description": "Optional OData query params ($filter, $select, $top, $skip, etc.)"
                                    }
                                },
                                "required": ["entity"]
                            }
                        },
                        {
                            "name": "create_s4hana_entity",
                            "description": "Create S/4HANA entities (Sales Orders: salesorders, salesorderitems | Business Partners: businesspartneraddresses, businesspartnercontacts)",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "entity": {
                                        "type": "string", 
                                        "enum": list(ALL_ODATA_CREATE.keys())
                                    },
                                    "payload": {
                                        "type": "object", 
                                        "description": "Entity data to create"
                                    }
                                },
                                "required": ["entity", "payload"]
                            }
                        },
                        {
                            "name": "check_and_create_sales_orders",
                            "description": "PoC workflow: Check sales orders and create line items if lacking",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "customer_filter": {
                                        "type": "string",
                                        "description": "Optional filter for customer (e.g. 'Customer eq \"10100001\"')"
                                    },
                                    "min_orders": {
                                        "type": "integer",
                                        "description": "Minimum number of orders expected",
                                        "default": 1
                                    },
                                    "line_items_to_create": {
                                        "type": "array",
                                        "description": "Sales order line items to create if lacking",
                                        "items": {"type": "object"}
                                    }
                                },
                                "required": ["line_items_to_create"]
                            }
                        }
                    ]
                }
            }
            response = func.HttpResponse(json.dumps(mcp_response), mimetype="application/json")
            return add_cors_headers(response)
        else:
            # Simple tools list for non-MCP clients
            simple_response = {
                "tools": [
                    {"name": "query_s4hana", "description": "Query S/4HANA entities"},
                    {"name": "create_s4hana_entity", "description": "Create S/4HANA entities"}, 
                    {"name": "check_and_create_sales_orders", "description": "PoC workflow"}
                ]
            }
            response = func.HttpResponse(json.dumps(simple_response), mimetype="application/json")
            return add_cors_headers(response)
    
    # Default: OpenAPI schema for non-JSON requests
    openapi_schema = {
        "openapi": "3.0.0",
        "info": {
            "title": "S/4HANA On-Premises MCP Server",
            "version": "1.0.0",
            "description": "Combined Business Partner & Sales Order MCP Tools for S/4HANA On-Premises"
        },
        "paths": {
            "/sse": {
                "post": {
                    "operationId": "mcp_protocol",
                    "summary": "MCP JSON-RPC Protocol Endpoint",
                    "description": "Handle MCP protocol messages"
                }
            }
        }
    }
    response = func.HttpResponse(json.dumps(openapi_schema), mimetype="application/json")
    return add_cors_headers(response)

# --- Remove separate query, create, workflow handlers and consolidate into SSE ---
# --- MCP Server-Sent Events Endpoint (Main MCP Protocol Handler) ---
@app.route(route="sse", methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"])
async def mcp_sse_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """MCP Server-Sent Events endpoint for MCP protocol"""
    
    if req.method == "OPTIONS":
        response = func.HttpResponse("")
        return add_cors_headers(response)
    
    # Handle MCP protocol messages
    if req.method in ["POST", "PUT", "PATCH"]:
        try:
            raw_body = req.get_body()
            logging.info(f"[MCP SSE] Incoming {req.method}: {raw_body}")
            body = req.get_json()
            
            if not body or body.get("jsonrpc") != "2.0":
                response = func.HttpResponse(
                    json.dumps({"error": "Invalid JSON-RPC 2.0 request"}),
                    mimetype="application/json",
                    status_code=400
                )
                return add_cors_headers(response)
            
            method = body.get("method", "")
            msg_id = body.get("id")
            
            # Handle MCP initialization
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {
                                "listChanged": False
                            }
                        },
                        "serverInfo": {
                            "name": "S/4HANA MCP Server",
                            "version": "1.0.0"
                        }
                    }
                }
                http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
                return add_cors_headers(http_response)
            
            # Handle initialized notification
            elif method == "initialized":
                response = func.HttpResponse("", status_code=200)
                return add_cors_headers(response)
            
            # Handle tools/list request
            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "tools": [
                            {
                                "name": "query_s4hana",
                                "description": "Query S/4HANA entities (Business Partners: businesspartners, customers, suppliers | Sales Orders: salesorders, salesorderitems, salesorderheaderpartners)",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "entity": {
                                            "type": "string",
                                            "description": "S/4HANA OData entity name",
                                            "enum": list(ALL_ODATA.keys())
                                        },
                                        "query": {
                                            "type": "string",
                                            "description": "Optional OData query params ($filter, $select, $top, $skip, etc.)"
                                        }
                                    },
                                    "required": ["entity"]
                                }
                            },
                            {
                                "name": "create_s4hana_entity",
                                "description": "Create S/4HANA entities (Sales Orders: salesorders, salesorderitems | Business Partners: businesspartneraddresses, businesspartnercontacts)",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "entity": {
                                            "type": "string", 
                                            "enum": list(ALL_ODATA_CREATE.keys())
                                        },
                                        "payload": {
                                            "type": "object", 
                                            "description": "Entity data to create"
                                        }
                                    },
                                    "required": ["entity", "payload"]
                                }
                            },
                            {
                                "name": "check_and_create_sales_orders",
                                "description": "PoC workflow: Check sales orders and create line items if lacking",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "customer_filter": {
                                            "type": "string",
                                            "description": "Optional filter for customer (e.g. 'Customer eq \"10100001\"')"
                                        },
                                        "min_orders": {
                                            "type": "integer",
                                            "description": "Minimum number of orders expected",
                                            "default": 1
                                        },
                                        "line_items_to_create": {
                                            "type": "array",
                                            "description": "Sales order line items to create if lacking",
                                            "items": {"type": "object"}
                                        }
                                    },
                                    "required": ["line_items_to_create"]
                                }
                            }
                        ]
                    }
                }
                http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
                return add_cors_headers(http_response)
            
            # Handle tools/call request
            elif method == "tools/call":
                # Support both MCP format and simplified Copilot Studio format
                # MCP format: {"params": {"name": "tool_name", "arguments": {...}}}
                # Simplified format: {"tool_name": "...", "entity": "...", "query": "..."}
                
                # Try MCP format first
                params = body.get("params", {})
                if params and "name" in params:
                    # Standard MCP format
                    tool_name = params.get("name", "")
                    arguments = params.get("arguments", {})
                else:
                    # Simplified Copilot Studio format
                    tool_name = body.get("tool_name", "")
                    # Build arguments from flat parameters
                    arguments = {}
                    if body.get("entity"):
                        arguments["entity"] = body.get("entity")
                    if body.get("query"):
                        arguments["query"] = body.get("query")
                    if body.get("payload"):
                        arguments["payload"] = body.get("payload")
                    if body.get("customer_filter"):
                        arguments["customer_filter"] = body.get("customer_filter")
                    if body.get("min_orders"):
                        arguments["min_orders"] = body.get("min_orders")
                    if body.get("line_items_to_create"):
                        arguments["line_items_to_create"] = body.get("line_items_to_create")
                
                logging.info(f"[MCP SSE] Tool execution - Name: {tool_name}, Arguments: {arguments}")
                
                if tool_name == "query_s4hana":
                    return await handle_query_tool(msg_id, arguments)
                elif tool_name == "create_s4hana_entity":
                    return await handle_create_tool(msg_id, arguments)
                elif tool_name == "check_and_create_sales_orders":
                    return await handle_workflow_tool(msg_id, arguments)
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {
                            "code": -32601,
                            "message": f"Unknown tool: {tool_name}",
                            "data": {
                                "available_tools": ["query_s4hana", "create_s4hana_entity", "check_and_create_sales_orders"]
                            }
                        }
                    }
                    http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
                    return add_cors_headers(http_response)
            else:
                # Handle unknown method
                response = {
                    "jsonrpc": "2.0", 
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}",
                        "data": {
                            "supported_methods": ["initialize", "initialized", "tools/list", "tools/call"]
                        }
                    }
                }
                http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
                return add_cors_headers(http_response)
                
        except Exception as e:
            logging.exception("[Error] MCP SSE endpoint failed")
            response = func.HttpResponse(f"Internal server error: {str(e)}", status_code=500)
            return add_cors_headers(response)
    
    # For GET requests, return a simple status
    response = func.HttpResponse(
        json.dumps({"status": "MCP Server Ready", "protocol": "2024-11-05"}),
        mimetype="application/json"
    )
    return add_cors_headers(response)

# --- Helper functions for tool handling ---
async def handle_query_tool(msg_id, arguments):
    """Handle query_s4hana tool calls"""
    try:
        entity = arguments.get("entity", "").lower()
        query = arguments.get("query", "")
        
        if entity not in ALL_ODATA:
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32602,
                    "message": f"Invalid entity '{entity}'. Allowed: {list(ALL_ODATA.keys())}"
                }
            }
            http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
            return add_cors_headers(http_response)
        
        resp = await fetch_odata_response(entity, query)
        if resp.status_code == 200:
            data = json.loads(resp.get_body().decode())
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(data, indent=2)}]
                }
            }
            http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
            return add_cors_headers(http_response)
        else:
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": resp.status_code,
                    "message": f"S/4HANA query failed: {resp.get_body().decode()}"
                }
            }
            http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
            return add_cors_headers(http_response)
    except Exception as e:
        logging.exception("[Error] Query tool failed")
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
        }
        http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
        return add_cors_headers(http_response)

async def handle_create_tool(msg_id, arguments):
    """Handle create_s4hana_entity tool calls"""
    try:
        entity = arguments.get("entity", "").lower()
        payload = arguments.get("payload", {})
        
        if entity not in ALL_ODATA_CREATE:
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32602,
                    "message": f"Invalid creatable entity '{entity}'. Allowed: {list(ALL_ODATA_CREATE.keys())}"
                }
            }
            http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
            return add_cors_headers(http_response)
        
        resp = await post_odata_entity(entity, payload)
        if resp.status_code in (200, 201):
            result = json.loads(resp.get_body().decode())
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
                }
            }
            http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
            return add_cors_headers(http_response)
        else:
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": resp.status_code,
                    "message": f"S/4HANA create failed: {resp.get_body().decode()}"
                }
            }
            http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
            return add_cors_headers(http_response)
    except Exception as e:
        logging.exception("[Error] Create tool failed")
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
        }
        http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
        return add_cors_headers(http_response)

async def handle_workflow_tool(msg_id, arguments):
    """Handle check_and_create_sales_orders workflow tool calls"""
    try:
        customer_filter = arguments.get("customer_filter", "")
        min_orders = arguments.get("min_orders", 1)
        line_items_to_create = arguments.get("line_items_to_create", [])
        
        # Step 1: Query existing sales orders
        query_params = f"$top=100"
        if customer_filter:
            query_params += f"&$filter={customer_filter}"
        
        resp = await fetch_odata_response("salesorders", query_params)
        if resp.status_code != 200:
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": resp.status_code,
                    "message": f"Failed to query sales orders: {resp.get_body().decode()}"
                }
            }
            http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
            return add_cors_headers(http_response)
        
        sales_orders = json.loads(resp.get_body().decode())
        orders_count = len(sales_orders)
        
        workflow_result = {
            "step1_query": {
                "existing_orders_count": orders_count,
                "min_required": min_orders,
                "orders": sales_orders[:5]  # Show first 5 for preview
            }
        }
        
        # Step 2: Check if we need to create orders
        if orders_count < min_orders:
            logging.info(f"[WORKFLOW] Only {orders_count} orders found, need {min_orders}. Creating line items...")
            
            created_items = []
            for item_payload in line_items_to_create:
                create_resp = await post_odata_entity("salesorderitems", item_payload)
                if create_resp.status_code in (200, 201):
                    created_item = json.loads(create_resp.get_body().decode())
                    created_items.append(created_item)
                else:
                    created_items.append({
                        "error": f"Failed to create: {create_resp.get_body().decode()}"
                    })
            
            workflow_result["step2_create"] = {
                "action": "created_line_items",
                "items_created": len(created_items),
                "results": created_items
            }
        else:
            workflow_result["step2_create"] = {
                "action": "no_creation_needed",
                "reason": f"Found {orders_count} orders >= {min_orders} minimum"
            }
        
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(workflow_result, indent=2)}]
            }
        }
        http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
        return add_cors_headers(http_response)
        
    except Exception as e:
        logging.exception("[Error] Workflow tool failed")
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
        }
        http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
        return add_cors_headers(http_response)

# --- SAP OData Helper Functions ---
async def fetch_odata_response(entity: str, query: str = "") -> func.HttpResponse:
    """Fetch data from S/4HANA OData endpoints"""
    url = ALL_ODATA.get(entity)
    if query:
        url = f"{url}?{query}"
    
    user = os.getenv("SAP_USER")
    pwd = os.getenv("SAP_PASS")
    if not user or not pwd:
        return func.HttpResponse("Missing SAP_USER or SAP_PASS environment variables", status_code=500)
    
    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
            r = await client.get(url, auth=(user, pwd), headers={"Accept": "application/xml"})
        
        if r.status_code != 200:
            logging.error(f"[S/4HANA ERROR {r.status_code}] {r.text}")
            return func.HttpResponse(r.text, status_code=r.status_code)
        
        # Parse XML response to JSON
        parsed = xmltodict.parse(r.text)
        entries = parsed.get("feed", {}).get("entry", [])
        if isinstance(entries, dict):
            entries = [entries]
        
        results = []
        for entry in entries:
            properties = entry.get("content", {}).get("m:properties", {})
            results.append(properties)
        
        return func.HttpResponse(json.dumps(results), mimetype="application/json")
        
    except httpx.RequestError as e:
        logging.exception("[RequestError] S/4HANA OData unreachable")
        return func.HttpResponse(f"S/4HANA connection error: {e}", status_code=500)
    except Exception as e:
        logging.exception("[Exception] S/4HANA OData parse error")
        return func.HttpResponse(f"S/4HANA processing error: {e}", status_code=500)

async def post_odata_entity(entity: str, payload: dict) -> func.HttpResponse:
    """Create entity in S/4HANA via OData POST with CSRF token"""
    url = ALL_ODATA_CREATE.get(entity)
    if not url:
        return func.HttpResponse(f"Entity '{entity}' not found in create mappings", status_code=400)
    
    user = os.getenv("SAP_USER")
    pwd = os.getenv("SAP_PASS")
    if not user or not pwd:
        return func.HttpResponse("Missing SAP_USER or SAP_PASS environment variables", status_code=500)
    
    try:
        # Increase timeout to 60 seconds for S/4HANA operations
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            # Step 1: Get CSRF token with HEAD/GET request
            logging.info(f"[CREATE] Fetching CSRF token for {entity}...")
            csrf_response = await client.get(
                url,
                auth=(user, pwd),
                headers={
                    "X-CSRF-Token": "Fetch",
                    "Accept": "application/json"
                }
            )
            
            # Extract CSRF token from response headers
            csrf_token = csrf_response.headers.get("X-CSRF-Token", "")
            cookies = csrf_response.cookies
            
            if not csrf_token:
                return func.HttpResponse("Failed to fetch CSRF token from S/4HANA", status_code=500)
            
            logging.info(f"[CSRF] Got token: {csrf_token[:20]}... for {entity}")
            
            # Step 2: Create entity with CSRF token
            logging.info(f"[CREATE] Posting to {entity} with payload: {json.dumps(payload)}")
            r = await client.post(
                url,
                auth=(user, pwd),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-CSRF-Token": csrf_token,
                    "X-Requested-With": "XMLHttpRequest"
                },
                cookies=cookies,  # Include session cookies
                json=payload
            )
            
            logging.info(f"[CREATE] S/4HANA responded with status: {r.status_code}")
        
        if r.status_code not in (200, 201):
            logging.error(f"[S/4HANA CREATE ERROR {r.status_code}] {r.text}")
            return func.HttpResponse(r.text, status_code=r.status_code)
        
        logging.info(f"[CREATE] Successfully created {entity}")
        return func.HttpResponse(r.text, mimetype="application/json", status_code=r.status_code)
        
    except httpx.ReadTimeout as e:
        logging.error(f"[TIMEOUT] S/4HANA took >60s to respond for {entity} creation")
        return func.HttpResponse(f"S/4HANA timeout: The system took too long to process the {entity} creation request. This may indicate the entity type is not supported for creation in this S/4HANA system.", status_code=408)
    except httpx.RequestError as e:
        logging.exception("[RequestError] S/4HANA OData unreachable")
        return func.HttpResponse(f"S/4HANA connection error: {e}", status_code=500)
    except Exception as e:
        logging.exception("[Exception] S/4HANA OData POST error")
        return func.HttpResponse(f"S/4HANA creation error: {e}", status_code=500)

# --- MCP PROTOCOL ENDPOINTS ONLY ---
# This is a pure MCP server implementation for both GitHub Copilot and Copilot Studio

# --- HEALTH CHECK ENDPOINT ---
@app.route(route="health", methods=["GET"])
async def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint for monitoring"""
    try:
        # Basic health check
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0",
            "endpoints": {
                "mcp_protocol": "/api/sse",
                "tools_discovery": "/api/tools",
                "copilot_studio": "/api/query-sales-orders"
            }
        }
        
        # Optional: Test SAP connectivity
        sap_user = os.getenv("SAP_USER")
        sap_pass = os.getenv("SAP_PASS")
        
        if sap_user and sap_pass:
            health_status["sap_config"] = "configured"
        else:
            health_status["sap_config"] = "missing_credentials"
            health_status["status"] = "degraded"
        
        status_code = 200 if health_status["status"] == "healthy" else 503
        response = func.HttpResponse(json.dumps(health_status), 
                                   mimetype="application/json", 
                                   status_code=status_code)
        return add_cors_headers(response)
        
    except Exception as e:
        logging.exception("[Error] Health check failed")
        error_response = {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        response = func.HttpResponse(json.dumps(error_response), 
                                   mimetype="application/json", 
                                   status_code=503)
        return add_cors_headers(response)

# --- COPILOT STUDIO SPECIFIC ENDPOINTS ---
@app.route(route="query-sales-orders", methods=["POST", "OPTIONS"])
async def query_sales_orders_copilot(req: func.HttpRequest) -> func.HttpResponse:
    """Copilot Studio compatible endpoint for querying sales orders"""
    
    if req.method == "OPTIONS":
        response = func.HttpResponse("")
        return add_cors_headers(response)
    
    try:
        body = req.get_json() or {}
        customer = body.get("customer", "")
        top = body.get("top", 10)
        order_by = body.get("orderBy", "TotalNetAmount desc")
        
        # Build OData query
        query_params = f"$top={top}&$orderby={order_by}"
        if customer:
            query_params += f"&$filter=SoldToParty eq '{customer}'"
        
        # Use existing fetch function
        resp = await fetch_odata_response("salesorders", query_params)
        
        if resp.status_code == 200:
            return add_cors_headers(resp)
        else:
            error_response = func.HttpResponse(
                json.dumps({"error": f"Failed to query sales orders: {resp.get_body().decode()}"}),
                mimetype="application/json",
                status_code=resp.status_code
            )
            return add_cors_headers(error_response)
            
    except Exception as e:
        logging.exception("[Error] Query sales orders failed")
        error_response = func.HttpResponse(
            json.dumps({"error": f"Internal error: {str(e)}"}),
            mimetype="application/json",
            status_code=500
        )
        return add_cors_headers(error_response)

@app.route(route="query-business-partners", methods=["POST", "OPTIONS"])
async def query_business_partners_copilot(req: func.HttpRequest) -> func.HttpResponse:
    """Copilot Studio compatible endpoint for querying business partners"""
    
    if req.method == "OPTIONS":
        response = func.HttpResponse("")
        return add_cors_headers(response)
    
    try:
        body = req.get_json() or {}
        filter_expr = body.get("filter", "")
        top = body.get("top", 10)
        
        # Build OData query
        query_params = f"$top={top}"
        if filter_expr:
            query_params += f"&$filter={filter_expr}"
        
        # Use existing fetch function
        resp = await fetch_odata_response("businesspartners", query_params)
        
        if resp.status_code == 200:
            return add_cors_headers(resp)
        else:
            error_response = func.HttpResponse(
                json.dumps({"error": f"Failed to query business partners: {resp.get_body().decode()}"}),
                mimetype="application/json",
                status_code=resp.status_code
            )
            return add_cors_headers(error_response)
            
    except Exception as e:
        logging.exception("[Error] Query business partners failed")
        error_response = func.HttpResponse(
            json.dumps({"error": f"Internal error: {str(e)}"}),
            mimetype="application/json",
            status_code=500
        )
        return add_cors_headers(error_response)

@app.route(route="create-sales-order", methods=["POST", "OPTIONS"])
async def create_sales_order_copilot(req: func.HttpRequest) -> func.HttpResponse:
    """Copilot Studio compatible endpoint for creating sales orders"""
    
    if req.method == "OPTIONS":
        response = func.HttpResponse("")
        return add_cors_headers(response)
    
    try:
        body = req.get_json() or {}
        sold_to_party = body.get("soldToParty", "")
        sales_order_type = body.get("salesOrderType", "OR")
        items = body.get("items", [])
        
        if not sold_to_party:
            error_response = func.HttpResponse(
                json.dumps({"error": "soldToParty is required"}),
                mimetype="application/json",
                status_code=400
            )
            return add_cors_headers(error_response)
        
        # Create sales order payload
        sales_order_payload = {
            "SoldToParty": sold_to_party,
            "SalesOrderType": sales_order_type,
            "TransactionCurrency": "USD"
        }
        
        # Use existing create function
        resp = await post_odata_entity("salesorders", sales_order_payload)
        
        if resp.status_code in (200, 201):
            return add_cors_headers(resp)
        else:
            error_response = func.HttpResponse(
                json.dumps({"error": f"Failed to create sales order: {resp.get_body().decode()}"}),
                mimetype="application/json",
                status_code=resp.status_code
            )
            return add_cors_headers(error_response)
            
    except Exception as e:
        logging.exception("[Error] Create sales order failed")
        error_response = func.HttpResponse(
            json.dumps({"error": f"Internal error: {str(e)}"}),
            mimetype="application/json",
            status_code=500
        )
        return add_cors_headers(error_response)