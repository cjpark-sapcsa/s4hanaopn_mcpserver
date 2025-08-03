import os
import json
import xmltodict
import logging
import requests
from datetime import datetime, timezone
import azure.functions as func
import httpx
from azure.storage.blob import BlobServiceClient

# --- Configuration ---
SAP_BASE_URL = os.getenv("SAP_BASE_URL", "http://your-s4hana-server:port")
FUNCTION_APP_BASE_URL = os.getenv("FUNCTION_APP_BASE_URL", "https://your-function-app.azurewebsites.net")
SAP_BP_SERVICE = f"{SAP_BASE_URL}/sap/opu/odata/sap/API_BUSINESS_PARTNER"
SAP_SO_SERVICE = f"{SAP_BASE_URL}/sap/opu/odata/sap/API_SALES_ORDER_SRV"

# --- Azure Blob Storage Configuration ---
BLOB_STORAGE_URL = os.getenv("BLOB_STORAGE_URL", "https://your-storage-account.blob.core.windows.net/salesorderrequest")
BLOB_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
BLOB_CONTAINER_NAME = os.getenv("BLOB_CONTAINER_NAME", "salesorderrequest")

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

# --- Azure Blob Storage Helper Functions ---
def get_blob_service_client():
    """Get Azure Blob Storage client"""
    try:
        if BLOB_CONNECTION_STRING:
            return BlobServiceClient.from_connection_string(BLOB_CONNECTION_STRING)
        else:
            # Fallback to default credential (for managed identity)
            from azure.identity import DefaultAzureCredential
            credential = DefaultAzureCredential()
            storage_account_url = os.getenv("BLOB_STORAGE_ACCOUNT_URL", "https://your-storage-account.blob.core.windows.net")
            return BlobServiceClient(
                account_url=storage_account_url,
                credential=credential
            )
    except Exception as e:
        logging.error(f"Failed to create blob service client: {str(e)}")
        return None

async def save_approval_request_to_blob(request_id: str, request_data: dict) -> bool:
    """Save approval request to Azure Blob Storage"""
    try:
        blob_service_client = get_blob_service_client()
        if not blob_service_client:
            return False
            
        blob_name = f"{request_id}.json"
        blob_client = blob_service_client.get_blob_client(
            container=BLOB_CONTAINER_NAME, 
            blob=blob_name
        )
        
        # Add metadata
        request_data["last_updated"] = datetime.now(timezone.utc).isoformat()
        
        # Upload as JSON
        json_data = json.dumps(request_data, indent=2)
        blob_client.upload_blob(json_data, overwrite=True)
        
        logging.info(f"[BLOB STORAGE] Saved approval request {request_id} to blob storage")
        return True
        
    except Exception as e:
        logging.error(f"[BLOB STORAGE ERROR] Failed to save {request_id}: {str(e)}")
        return False

async def get_approval_request_from_blob(request_id: str) -> dict:
    """Get approval request from Azure Blob Storage"""
    try:
        blob_service_client = get_blob_service_client()
        if not blob_service_client:
            return {}
            
        blob_name = f"{request_id}.json"
        blob_client = blob_service_client.get_blob_client(
            container=BLOB_CONTAINER_NAME, 
            blob=blob_name
        )
        
        # Download blob content
        blob_data = blob_client.download_blob().readall()
        request_data = json.loads(blob_data.decode('utf-8'))
        
        logging.info(f"[BLOB STORAGE] Retrieved approval request {request_id} from blob storage")
        return request_data
        
    except Exception as e:
        logging.error(f"[BLOB STORAGE ERROR] Failed to retrieve {request_id}: {str(e)}")
        return {}

async def list_approval_requests_from_blob() -> list:
    """List all approval requests from Azure Blob Storage"""
    try:
        blob_service_client = get_blob_service_client()
        if not blob_service_client:
            return []
            
        container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)
        
        requests = []
        for blob in container_client.list_blobs():
            if blob.name.endswith('.json'):
                try:
                    blob_client = blob_service_client.get_blob_client(
                        container=BLOB_CONTAINER_NAME, 
                        blob=blob.name
                    )
                    blob_data = blob_client.download_blob().readall()
                    request_data = json.loads(blob_data.decode('utf-8'))
                    requests.append(request_data)
                except Exception as blob_error:
                    logging.warning(f"[BLOB STORAGE] Failed to read blob {blob.name}: {str(blob_error)}")
                    continue
        
        logging.info(f"[BLOB STORAGE] Retrieved {len(requests)} approval requests from blob storage")
        return requests
        
    except Exception as e:
        logging.error(f"[BLOB STORAGE ERROR] Failed to list approval requests: {str(e)}")
        return []

async def update_approval_request_in_blob(request_id: str, updates: dict) -> bool:
    """Update existing approval request in Azure Blob Storage"""
    try:
        # Get existing data
        existing_data = await get_approval_request_from_blob(request_id)
        if not existing_data:
            return False
            
        # Apply updates
        existing_data.update(updates)
        existing_data["last_updated"] = datetime.now(timezone.utc).isoformat()
        
        # Save back to blob
        return await save_approval_request_to_blob(request_id, existing_data)
        
    except Exception as e:
        logging.error(f"[BLOB STORAGE ERROR] Failed to update {request_id}: {str(e)}")
        return False

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
@app.route(route="sse", methods=["POST", "OPTIONS"])
async def mcp_sse_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """MCP Server-Sent Events endpoint for MCP protocol"""
    
    if req.method == "OPTIONS":
        response = func.HttpResponse("")
        return add_cors_headers(response)
    
    # Handle MCP protocol messages
    if req.method == "POST":
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
                            },
                            {
                                "name": "check_approval_status",
                                "description": "Check the approval status of a sales order request",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "request_id": {
                                            "type": "string",
                                            "description": "The approval request ID to check"
                                        }
                                    },
                                    "required": ["request_id"]
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
                elif tool_name == "check_approval_status":
                    return await handle_approval_status_tool(msg_id, arguments)
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {
                            "code": -32601,
                            "message": f"Unknown tool: {tool_name}",
                            "data": {
                                "available_tools": ["query_s4hana", "create_s4hana_entity", "check_and_create_sales_orders", "check_approval_status"]
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
    
    # For other requests, return a simple status
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
        
        # CHECK: If creating a sales order, trigger approval workflow instead of direct creation
        if entity == "salesorders":
            logging.info("[APPROVAL TRIGGER] Sales order creation detected - routing to approval workflow")
            
            # Generate unique request ID
            request_id = f"SO-REQ-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            
            # Store approval request in Azure Blob Storage
            approval_request_data = {
                "id": request_id,
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": payload.get("created_by", "MCP_Client"),
                "sales_order_data": payload,
                "justification": payload.get("justification", "Sales order created via MCP client"),
                "approver": "CJ Park",
                "approver_email": "approver@yourcompany.com"
            }
            
            # Save to blob storage for persistence across function restarts
            blob_saved = await save_approval_request_to_blob(request_id, approval_request_data)
            
            # Also keep in memory for current session (faster access)
            approval_requests[request_id] = approval_request_data
            
            # Send notification to approver
            subject = f"🔔 Sales Order Approval Required - {request_id}"
            message = f"""
            A new sales order requires your approval:
            
            Request ID: {request_id}
            Customer: {payload.get('SoldToParty', 'N/A')}
            Order Type: {payload.get('SalesOrderType', 'N/A')}
            Currency: {payload.get('TransactionCurrency', 'N/A')}
            PO Number: {payload.get('CustomerPurchaseOrderNumber', 'N/A')}
            Delivery Date: {payload.get('RequestedDeliveryDate', 'N/A')}
            
            Please review and approve/reject this request.
            Approve URL: {FUNCTION_APP_BASE_URL}/approve-request?request_id={request_id}
            """
            
            # Send notifications
            email_sent = send_notification("approver@yourcompany.com", subject, message)
            
            # Prepare Teams notification data
            teams_data = {
                "request_id": request_id,
                "customer": payload.get('SoldToParty', 'N/A'),
                "amount": payload.get('TotalNetAmount', 'Pending calculation'),
                "justification": payload.get('justification', 'Sales order created via MCP client'),
                "created_by": payload.get("created_by", "MCP_Client"),
                "created_at": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
                "approver": "CJ Park",
                "order_type": payload.get('SalesOrderType', 'N/A'),
                "currency": payload.get('TransactionCurrency', 'N/A'),
                "po_number": payload.get('CustomerPurchaseOrderNumber', 'N/A')
            }
            
            # Get Teams webhook from environment or use test URL
            teams_webhook = os.getenv("TEAMS_WEBHOOK_URL", "https://test-webhook-url")
            teams_sent = send_teams_notification(teams_webhook, teams_data)
            
            # Return approval pending response instead of creating directly
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{
                        "type": "text", 
                        "text": json.dumps({
                            "status": "approval_required",
                            "message": "Sales order creation request submitted for approval",
                            "request_id": request_id,
                            "approval_status": "pending",
                            "notifications_sent": {
                                "email": email_sent,
                                "teams": teams_sent
                            },
                            "approve_url": f"{FUNCTION_APP_BASE_URL}/approve-request",
                            "approver": "CJ Park",
                            "next_steps": "Wait for approval notification. The sales order will be created automatically once approved."
                        }, indent=2)
                    }]
                }
            }
            http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
            return add_cors_headers(http_response)
        
        # For non-sales order entities, proceed with direct creation (no approval needed)
        resp = await post_odata_entity(entity, payload, bypass_approval=True)
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
                create_resp = await post_odata_entity("salesorderitems", item_payload, bypass_approval=True)
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

async def handle_approval_status_tool(msg_id, arguments):
    """Handle check_approval_status tool calls"""
    try:
        request_id = arguments.get("request_id", "")
        
        if not request_id:
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32602,
                    "message": "Missing required parameter: request_id"
                }
            }
            http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
            return add_cors_headers(http_response)
        
        # Check in memory first, then blob storage if not found
        approval_data = None
        if request_id in approval_requests:
            approval_data = approval_requests[request_id]
        else:
            # Try to get from blob storage
            approval_data = await get_approval_request_from_blob(request_id)
            if approval_data:
                # Cache in memory for faster future access
                approval_requests[request_id] = approval_data
        
        if not approval_data:
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{
                        "type": "text",
                        "text": json.dumps({
                            "status": "not_found",
                            "message": f"Approval request {request_id} not found in memory or blob storage",
                            "request_id": request_id
                        }, indent=2)
                    }]
                }
            }
            http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
            return add_cors_headers(http_response)
        
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{
                    "type": "text",
                    "text": json.dumps({
                        "request_id": request_id,
                        "status": approval_data.get("status", "unknown"),
                        "created_at": approval_data.get("created_at", ""),
                        "created_by": approval_data.get("created_by", ""),
                        "approver": approval_data.get("approver", ""),
                        "approved_at": approval_data.get("approved_at", ""),
                        "approver_comments": approval_data.get("approver_comments", ""),
                        "sales_order_data": approval_data.get("sales_order_data", {}),
                        "justification": approval_data.get("justification", "")
                    }, indent=2)
                }]
            }
        }
        http_response = func.HttpResponse(json.dumps(response), mimetype="application/json")
        return add_cors_headers(http_response)
        
    except Exception as e:
        logging.exception("[Error] Approval status tool failed")
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

async def post_odata_entity(entity: str, payload: dict, bypass_approval: bool = False) -> func.HttpResponse:
    """Create entity in S/4HANA via OData POST with CSRF token
    
    Args:
        entity: The entity type to create
        payload: The data payload 
        bypass_approval: ONLY set to True by the approval handler after approval is granted
    """
    url = ALL_ODATA_CREATE.get(entity)
    if not url:
        return func.HttpResponse(f"Entity '{entity}' not found in create mappings", status_code=400)
    
    # 🔒 SECURITY ENFORCEMENT: Block direct sales order creation unless approved
    if entity.lower() == "salesorders" and not bypass_approval:
        logging.warning(f"[SECURITY BLOCK] Attempted direct sales order creation without approval - BLOCKED")
        logging.warning(f"[SECURITY BLOCK] Payload: {json.dumps(payload)}")
        
        # Return security error
        security_error = {
            "error": "SECURITY_VIOLATION",
            "message": "Direct sales order creation is not allowed. All sales orders must go through the approval workflow.",
            "required_action": "Use the MCP protocol endpoint (/api/sse) or Copilot Studio endpoint (/api/create-sales-order) which enforce approval workflow",
            "governance_policy": "All sales order creation requires manager approval as per company policy",
            "blocked_at": datetime.now(timezone.utc).isoformat(),
            "entity_attempted": entity,
            "payload_summary": {
                "customer": payload.get("SoldToParty", "N/A"),
                "order_type": payload.get("SalesOrderType", "N/A"),
                "currency": payload.get("TransactionCurrency", "N/A")
            }
        }
        
        return func.HttpResponse(
            json.dumps(security_error, indent=2), 
            mimetype="application/json", 
            status_code=403  # Forbidden
        )
    
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
    """Copilot Studio compatible endpoint for creating sales orders - ENFORCES APPROVAL WORKFLOW"""
    
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
            "TransactionCurrency": "USD",
            "created_by": "Copilot_Studio",
            "justification": f"Sales order for customer {sold_to_party} via Copilot Studio"
        }
        
        # 🔒 SECURITY: ALWAYS go through approval workflow for sales orders
        logging.info("[SECURITY ENFORCEMENT] Copilot Studio sales order creation - routing through approval workflow")
        
        # Generate unique request ID
        request_id = f"SO-REQ-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        
        # Store approval request in Azure Blob Storage
        approval_request_data = {
            "id": request_id,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "Copilot_Studio",
            "sales_order_data": sales_order_payload,
            "justification": f"Sales order for customer {sold_to_party} via Copilot Studio",
            "approver": "CJ Park",
            "approver_email": "approver@yourcompany.com",
            "source": "copilot_studio_endpoint"
        }
        
        # Save to blob storage for persistence across function restarts
        blob_saved = await save_approval_request_to_blob(request_id, approval_request_data)
        
        # Also keep in memory for current session (faster access)
        approval_requests[request_id] = approval_request_data
        
        # Send notification to approver
        subject = f"🔔 Sales Order Approval Required - {request_id}"
        message = f"""
        A new sales order requires your approval (via Copilot Studio):
        
        Request ID: {request_id}
        Customer: {sold_to_party}
        Order Type: {sales_order_type}
        Currency: USD
        Source: Copilot Studio
        
        Please review and approve/reject this request.
        Approve URL: {FUNCTION_APP_BASE_URL}/approve-request?request_id={request_id}
        """
        
        # Send notifications
        email_sent = send_notification("approver@yourcompany.com", subject, message)
        
        # Prepare Teams notification data
        teams_data = {
            "request_id": request_id,
            "customer": sold_to_party,
            "amount": "Pending calculation",
            "justification": f"Sales order for customer {sold_to_party} via Copilot Studio",
            "created_by": "Copilot_Studio",
            "created_at": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            "approver": "CJ Park",
            "order_type": sales_order_type,
            "currency": "USD",
            "po_number": "N/A"
        }
        
        # Get Teams webhook from environment or use test URL
        teams_webhook = os.getenv("TEAMS_WEBHOOK_URL", "https://test-webhook-url")
        teams_sent = send_teams_notification(teams_webhook, teams_data)
        
        # Return approval pending response instead of creating directly
        response_data = {
            "status": "approval_required",
            "message": "Sales order creation request submitted for approval (Copilot Studio endpoint)",
            "request_id": request_id,
            "approval_status": "pending",
            "notifications_sent": {
                "email": email_sent,
                "teams": teams_sent
            },
            "approve_url": f"{FUNCTION_APP_BASE_URL}/approve-request",
            "approver": "CJ Park",
            "next_steps": "Wait for approval notification. The sales order will be created automatically once approved.",
            "security_note": "All sales order creation requests are subject to approval workflow"
        }
        
        response = func.HttpResponse(
            json.dumps(response_data, indent=2),
            mimetype="application/json",
            status_code=202  # 202 Accepted - request received, pending approval
        )
        return add_cors_headers(response)
            
    except Exception as e:
        logging.exception("[Error] Create sales order failed")
        error_response = func.HttpResponse(
            json.dumps({"error": f"Internal error: {str(e)}"}),
            mimetype="application/json",
            status_code=500
        )
        return add_cors_headers(error_response)

# =============================================================================
# ENHANCED APPROVAL WORKFLOW FUNCTIONS
# =============================================================================

# In-memory storage for approval requests (use Azure Storage or Database in production)
approval_requests = {}

def clean_sap_payload(payload: dict) -> dict:
    """Remove custom fields that are not recognized by SAP S/4HANA OData APIs and format data properly"""
    from datetime import datetime
    
    # List of known valid SAP S/4HANA Sales Order fields
    valid_sap_fields = {
        'SalesOrder', 'SalesOrderType', 'SalesOrganization', 'DistributionChannel', 
        'OrganizationDivision', 'SalesGroup', 'SalesOffice', 'SalesDistrict',
        'SoldToParty', 'CreationDate', 'CreatedByUser', 'LastChangeDate',
        'SenderBusinessSystemName', 'ExternalDocumentID', 'LastChangeDateTime',
        'ExternalDocLastChangeDateTime', 'PurchaseOrderByCustomer', 
        'PurchaseOrderByShipToParty', 'CustomerPurchaseOrderType',
        'CustomerPurchaseOrderDate', 'SalesOrderDate', 'TotalNetAmount',
        'OverallDeliveryStatus', 'TotalBlockStatus', 'OverallOrdReltdBillgStatus',
        'OverallSDDocReferenceStatus', 'TransactionCurrency', 'SDDocumentReason',
        'PricingDate', 'PriceDetnExchangeRate', 'BillingPlan', 'RequestedDeliveryDate',
        'ShippingCondition', 'CompleteDeliveryIsDefined', 'ShippingType',
        'HeaderBillingBlockReason', 'DeliveryBlockReason', 'DeliveryDateTypeRule',
        'IncotermsClassification', 'IncotermsTransferLocation', 'IncotermsLocation1',
        'IncotermsLocation2', 'IncotermsVersion', 'CustomerPriceGroup',
        'PriceListType', 'CustomerPaymentTerms', 'PaymentMethod', 'FixedValueDate',
        'AssignmentReference', 'ReferenceSDDocument', 'ReferenceSDDocumentCategory',
        'AccountingDocExternalReference', 'CustomerAccountAssignmentGroup',
        'AccountingExchangeRate', 'CorrespncExternalReference',
        'POCorrespncExternalReference', 'CustomerConditionGroup1', 'CustomerConditionGroup2',
        'CustomerConditionGroup3', 'CustomerConditionGroup4', 'CustomerConditionGroup5',
        'CustomerGroup', 'AdditionalCustomerGroup1', 'AdditionalCustomerGroup2',
        'AdditionalCustomerGroup3', 'AdditionalCustomerGroup4', 'AdditionalCustomerGroup5',
        'SlsDocIsRlvtForProofOfDeliv', 'CustomerTaxClassification1', 'CustomerTaxClassification2',
        'CustomerTaxClassification3', 'CustomerTaxClassification4', 'CustomerTaxClassification5',
        'CustomerTaxClassification6', 'CustomerTaxClassification7', 'CustomerTaxClassification8',
        'CustomerTaxClassification9', 'TaxDepartureCountry', 'VATRegistrationCountry',
        'SalesOrderApprovalReason', 'SalesDocApprovalStatus', 'OverallSDProcessStatus',
        'TotalCreditCheckStatus', 'OverallTotalDeliveryStatus', 'OverallSDDocumentRejectionSts',
        'BillingDocumentDate', 'ContractAccount', 'AdditionalValueDays',
        'CustomerPurchaseOrderSuplmnt', 'ServicesRenderedDate'
    }
    
    # Date fields that need special formatting for S/4HANA OData
    date_fields = {
        'RequestedDeliveryDate', 'SalesOrderDate', 'CustomerPurchaseOrderDate', 
        'PricingDate', 'CreationDate', 'LastChangeDate', 'BillingDocumentDate',
        'FixedValueDate', 'ServicesRenderedDate'
    }
    
    # Create clean payload with only valid SAP fields and proper formatting
    clean_payload = {}
    for key, value in payload.items():
        if key in valid_sap_fields:
            # Special handling for date fields
            if key in date_fields and value:
                try:
                    # Try to parse various date formats and convert to S/4HANA format
                    if isinstance(value, str):
                        # Try different date formats
                        for date_format in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f']:
                            try:
                                parsed_date = datetime.strptime(value, date_format)
                                # Convert to S/4HANA OData date format: /Date(timestamp)/
                                timestamp_ms = int(parsed_date.timestamp() * 1000)
                                clean_payload[key] = f"/Date({timestamp_ms})/"
                                logging.info(f"[DATE FORMAT] Converted {key}: {value} -> /Date({timestamp_ms})/")
                                break
                            except ValueError:
                                continue
                        else:
                            # If no format matched, try to keep original value
                            clean_payload[key] = value
                            logging.warning(f"[DATE FORMAT] Could not parse date {key}: {value}, keeping original")
                    else:
                        clean_payload[key] = value
                except Exception as e:
                    logging.warning(f"[DATE FORMAT ERROR] Failed to format {key}: {value}, error: {e}")
                    clean_payload[key] = value
            else:
                clean_payload[key] = value
        else:
            logging.info(f"[PAYLOAD CLEANUP] Removing custom field: {key} = {value}")
    
    return clean_payload

def send_notification(to_email: str, subject: str, message: str) -> bool:
    """Send email notification (mock implementation for testing)"""
    try:
        logging.info(f"📧 EMAIL NOTIFICATION SENT")
        logging.info(f"To: {to_email}")
        logging.info(f"Subject: {subject}")
        logging.info(f"Message: {message}")
        logging.info(f"🔔 POPUP NOTIFICATION: {subject}")
        
        # TODO: Integrate with actual email service (SendGrid, Outlook, etc.)
        # For testing, we'll just log the notification
        
        return True
    except Exception as e:
        logging.error(f"Failed to send notification: {str(e)}")
        return False

def send_teams_notification(webhook_url: str, request_data: dict) -> bool:
    """Send Teams notification using Power Automate webhook"""
    try:
        # Real Teams webhook implementation
        if webhook_url and webhook_url.startswith("https://"):
            # Send raw data to Power Automate for adaptive card population
            # Include the correct base URL for the Power Automate template to use
            payload = {
                "request_id": request_data.get("request_id", ""),
                "customer": request_data.get("customer", ""),
                "amount": request_data.get("amount", ""),
                "justification": request_data.get("justification", ""),
                "created_by": request_data.get("created_by", ""),
                "created_at": request_data.get("created_at", ""),
                "approver": request_data.get("approver", ""),
                "order_type": request_data.get("order_type", "OR"),
                "currency": request_data.get("currency", "USD"),
                "po_number": request_data.get("po_number", "N/A"),
                "base_url": FUNCTION_APP_BASE_URL,  # Provide base URL for Power Automate template
                "approve_url": f"{FUNCTION_APP_BASE_URL}/approve-request?request_id={request_data.get('request_id', '')}",
                "reject_url": f"{FUNCTION_APP_BASE_URL}/reject-request?request_id={request_data.get('request_id', '')}"
            }
            
            # Send to Teams
            response = requests.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 202:  # Power Automate returns 202 Accepted
                logging.info(f"� REAL TEAMS NOTIFICATION SENT to SalesOrderAgent channel")
                logging.info(f"Response: {response.text}")
                return True
            else:
                logging.error(f"Teams webhook failed: {response.status_code} - {response.text}")
                return False
        else:
            # Fallback to mock for testing
            logging.info(f"📱 TEAMS NOTIFICATION SENT (Mock)")
            logging.info(f"Request Data: {request_data}")
            logging.info(f"🔔 POPUP NOTIFICATION: Sales Order Approval Request")
            return True
            
    except Exception as e:
        logging.error(f"Failed to send Teams notification: {str(e)}")
        return False

@app.route(route="create-so-request", methods=["POST", "OPTIONS"])
async def create_so_request(req: func.HttpRequest) -> func.HttpResponse:
    """Create a sales order request that requires approval"""
    
    if req.method == "OPTIONS":
        response = func.HttpResponse("")
        return add_cors_headers(response)
    
    try:
        body = req.get_json() or {}
        
        # Generate unique request ID
        request_id = f"SO-REQ-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        
        # Store approval request in Azure Blob Storage
        approval_request_data = {
            "id": request_id,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": body.get("created_by", "system"),
            "sales_order_data": body.get("sales_order_data", {}),
            "justification": body.get("justification", ""),
            "approver": "CJ Park",
            "approver_email": "approver@yourcompany.com"
        }
        
        # Save to blob storage for persistence across function restarts
        blob_saved = await save_approval_request_to_blob(request_id, approval_request_data)
        
        # Also keep in memory for current session (faster access)
        approval_requests[request_id] = approval_request_data
        
        # Send notification to approver
        subject = f"🔔 Sales Order Approval Required - {request_id}"
        message = f"""
        A new sales order requires your approval:
        
        Request ID: {request_id}
        Customer: {body.get('sales_order_data', {}).get('SoldToParty', 'N/A')}
        Amount: {body.get('sales_order_data', {}).get('TotalNetAmount', 'N/A')}
        Justification: {body.get('justification', 'None provided')}
        
        Please review and approve/reject this request.
        """
        
        # Send notifications
        email_sent = send_notification("approver@yourcompany.com", subject, message)
        
        # Prepare Teams notification data
        teams_data = {
            "request_id": request_id,
            "customer": body.get('sales_order_data', {}).get('SoldToParty', 'N/A'),
            "amount": body.get('sales_order_data', {}).get('TotalNetAmount', 'N/A'),
            "justification": body.get('justification', 'None provided'),
            "created_by": body.get("created_by", "system"),
            "created_at": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            "approver": "CJ Park"
        }
        
        # Get Teams webhook from environment or use test URL
        teams_webhook = os.getenv("TEAMS_WEBHOOK_URL", "https://test-webhook-url")
        teams_sent = send_teams_notification(teams_webhook, teams_data)
        
        response_data = {
            "request_id": request_id,
            "status": "pending",
            "message": "Sales order request created and approval notification sent",
            "notifications": {
                "email_sent": email_sent,
                "teams_sent": teams_sent
            }
        }
        
        response = func.HttpResponse(
            json.dumps(response_data),
            mimetype="application/json",
            status_code=201
        )
        return add_cors_headers(response)
        
    except Exception as e:
        logging.exception("[Error] Create SO request failed")
        error_response = func.HttpResponse(
            json.dumps({"error": f"Internal error: {str(e)}"}),
            mimetype="application/json",
            status_code=500
        )
        return add_cors_headers(error_response)

@app.route(route="approve-request", methods=["GET", "POST", "OPTIONS"])
async def approve_request(req: func.HttpRequest) -> func.HttpResponse:
    """Approve a sales order request and create the actual sales order"""
    
    if req.method == "OPTIONS":
        response = func.HttpResponse("")
        return add_cors_headers(response)
    
    try:
        logging.info(f"[APPROVE] Starting approval process - Method: {req.method}")
        
        # Handle both GET (Teams button) and POST (API) requests
        if req.method == "GET":
            # Teams button click - extract request_id from query parameters
            request_id = req.params.get("request_id", "")
            approver_comments = "Approved via Teams notification button"
            logging.info(f"[APPROVE] GET request - request_id: {request_id}")
            
            if not request_id:
                # Return user-friendly HTML page for missing request ID
                html_response = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Sales Order Approval</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 40px; }}
                        .error {{ color: red; }}
                        .container {{ max-width: 600px; margin: 0 auto; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h2>❌ Sales Order Approval Error</h2>
                        <p class="error">Missing request ID parameter.</p>
                        <p>Please use the direct approval link from the Teams notification.</p>
                    </div>
                </body>
                </html>
                """
                response = func.HttpResponse(html_response, mimetype="text/html", status_code=400)
                return add_cors_headers(response)
                
        else:  # POST request
            body = req.get_json() or {}
            request_id = body.get("request_id", "")
            approver_comments = body.get("comments", "Approved via API")
        
        # Check for approval request in memory first, then blob storage
        approval_data = None
        if request_id:
            # Try in-memory cache first
            logging.info(f"[APPROVE] Checking approval request {request_id}")
            
            # Initialize approval_requests if not exists (Azure Functions may reset memory)
            global approval_requests
            try:
                if request_id in approval_requests:
                    approval_data = approval_requests[request_id]
                    logging.info(f"[APPROVE] Found request {request_id} in memory cache")
                else:
                    # Try to get from blob storage
                    logging.info(f"[APPROVE] Request {request_id} not in memory, checking blob storage")
                    try:
                        approval_data = await get_approval_request_from_blob(request_id)
                        if approval_data:
                            # Cache in memory for faster future access
                            approval_requests[request_id] = approval_data
                            logging.info(f"[APPROVE] Found request {request_id} in blob storage")
                        else:
                            logging.warning(f"[APPROVE] Request {request_id} not found in blob storage")
                    except Exception as blob_error:
                        logging.error(f"[APPROVE] Blob storage error for {request_id}: {str(blob_error)}")
                        approval_data = None
            except Exception as e:
                logging.error(f"[APPROVE] Error accessing approval requests: {str(e)}")
                approval_data = None
        
        if not request_id or not approval_data:
            if req.method == "GET":
                # Return user-friendly HTML page for invalid request ID
                html_response = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Sales Order Approval</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 40px; }}
                        .error {{ color: red; }}
                        .container {{ max-width: 600px; margin: 0 auto; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h2>❌ Sales Order Approval Error</h2>
                        <p class="error">Request ID '{request_id}' not found or already processed.</p>
                        <p>The approval request may have expired or been processed already.</p>
                    </div>
                </body>
                </html>
                """
                response = func.HttpResponse(html_response, mimetype="text/html", status_code=404)
                return add_cors_headers(response)
            else:
                error_response = func.HttpResponse(
                    json.dumps({"error": "Invalid request ID"}),
                    mimetype="application/json",
                    status_code=404
                )
                return add_cors_headers(error_response)
        
        # Update approval status in memory and blob storage
        approval_data["status"] = "approved"
        approval_data["approved_at"] = datetime.now(timezone.utc).isoformat()
        approval_data["approver_comments"] = approver_comments
        
        # Update in memory
        approval_requests[request_id] = approval_data
        
        # Update in blob storage for persistence
        await update_approval_request_in_blob(request_id, {
            "status": "approved",
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "approver_comments": approver_comments
        })
        
        # Create the actual sales order
        sales_order_data = approval_data["sales_order_data"]
        
        # 🧹 CLEAN PAYLOAD: Remove custom fields that S/4HANA doesn't recognize
        clean_sales_order_data = clean_sap_payload(sales_order_data)
        
        try:
            # 🔓 APPROVED: Use bypass flag to allow creation after approval
            logging.info(f"[APPROVAL GRANTED] Creating approved sales order for request {request_id}")
            logging.info(f"[CLEANED PAYLOAD] Original: {json.dumps(sales_order_data)}")
            logging.info(f"[CLEANED PAYLOAD] Cleaned: {json.dumps(clean_sales_order_data)}")
            resp = await post_odata_entity("salesorders", clean_sales_order_data, bypass_approval=True)
            
            if resp.status_code in (200, 201):
                # Parse the created sales order response
                try:
                    created_so = json.loads(resp.get_body().decode())
                    sales_order_number = created_so.get('SalesOrder', 'N/A')
                except:
                    sales_order_number = 'Successfully created'
                
                # Send approval confirmation
                subject = f"✅ Sales Order Approved & Created - {request_id}"
                message = f"""
                Your sales order request has been approved and created:
                
                Request ID: {request_id}
                Sales Order: {sales_order_number}
                Status: APPROVED & CREATED
                Approver Comments: {approver_comments}
                """
                
                # Send confirmation notification
                send_notification(approval_data.get("created_by", "system"), subject, message)
                
                # Return appropriate response based on request method
                if req.method == "GET":
                    # Return user-friendly HTML page for Teams button click
                    html_response = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>Sales Order Approved</title>
                        <style>
                            body {{ font-family: Arial, sans-serif; margin: 40px; }}
                            .success {{ color: green; }}
                            .container {{ max-width: 600px; margin: 0 auto; }}
                            .details {{ background-color: #f5f5f5; padding: 15px; margin: 20px 0; border-radius: 5px; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h2>✅ Sales Order Approved Successfully!</h2>
                            <p class="success">The sales order has been approved and created in S/4HANA.</p>
                            <div class="details">
                                <h3>Approval Details:</h3>
                                <p><strong>Request ID:</strong> {request_id}</p>
                                <p><strong>Sales Order:</strong> {sales_order_number}</p>
                                <p><strong>Customer:</strong> {sales_order_data.get('SoldToParty', 'N/A')}</p>
                                <p><strong>Order Type:</strong> {sales_order_data.get('SalesOrderType', 'N/A')}</p>
                                <p><strong>Status:</strong> APPROVED & CREATED</p>
                                <p><strong>Approver Comments:</strong> {approver_comments}</p>
                            </div>
                            <p>You can close this window.</p>
                        </div>
                    </body>
                    </html>
                    """
                    response = func.HttpResponse(html_response, mimetype="text/html", status_code=200)
                    return add_cors_headers(response)
                else:
                    # Return JSON response for API calls
                    response_data = {
                        "status": "approved_and_created",
                        "request_id": request_id,
                        "sales_order": sales_order_number,
                        "message": "Sales order approved and successfully created",
                        "approver_comments": approver_comments
                    }
                    response = func.HttpResponse(json.dumps(response_data), mimetype="application/json")
                    return add_cors_headers(response)
            else:
                # S/4HANA creation failed
                error_msg = f"S/4HANA creation failed: {resp.get_body().decode()}"
                logging.error(f"[APPROVAL ERROR] {error_msg}")
                
                if req.method == "GET":
                    html_response = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>Sales Order Approval Error</title>
                        <style>
                            body {{ font-family: Arial, sans-serif; margin: 40px; }}
                            .error {{ color: red; }}
                            .container {{ max-width: 600px; margin: 0 auto; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h2>⚠️ Approval Error</h2>
                            <p class="error">The request was approved but S/4HANA creation failed.</p>
                            <p><strong>Request ID:</strong> {request_id}</p>
                            <p><strong>Error:</strong> {error_msg}</p>
                            <p>Please contact IT support.</p>
                        </div>
                    </body>
                    </html>
                    """
                    response = func.HttpResponse(html_response, mimetype="text/html", status_code=500)
                    return add_cors_headers(response)
                else:
                    error_response = func.HttpResponse(
                        json.dumps({"error": error_msg}),
                        mimetype="application/json",
                        status_code=resp.status_code
                    )
                    return add_cors_headers(error_response)
                    
        except Exception as so_error:
            logging.exception(f"[Error] Sales order creation failed for {request_id}")
            error_msg = f"Sales order creation error: {str(so_error)}"
            
            if req.method == "GET":
                html_response = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Sales Order Creation Error</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 40px; }}
                        .error {{ color: red; }}
                        .container {{ max-width: 600px; margin: 0 auto; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h2>❌ Creation Error</h2>
                        <p class="error">An error occurred while creating the sales order.</p>
                        <p><strong>Request ID:</strong> {request_id}</p>
                        <p><strong>Error:</strong> {error_msg}</p>
                        <p>Please contact IT support.</p>
                    </div>
                </body>
                </html>
                """
                response = func.HttpResponse(html_response, mimetype="text/html", status_code=500)
                return add_cors_headers(response)
            else:
                error_response = func.HttpResponse(
                    json.dumps({"error": error_msg}),
                    mimetype="application/json",
                    status_code=500
                )
                return add_cors_headers(error_response)
        
    except Exception as e:
        logging.exception("[Error] Approve request failed")
        
        if req.method == "GET":
            html_response = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Approval System Error</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 40px; }}
                    .error {{ color: red; }}
                    .container {{ max-width: 600px; margin: 0 auto; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>❌ System Error</h2>
                    <p class="error">An unexpected error occurred in the approval system.</p>
                    <p><strong>Error:</strong> {str(e)}</p>
                    <p>Please contact IT support.</p>
                </div>
            </body>
            </html>
            """
            response = func.HttpResponse(html_response, mimetype="text/html", status_code=500)
            return add_cors_headers(response)
        else:
            error_response = func.HttpResponse(
                json.dumps({"error": f"Internal error: {str(e)}"}),
                mimetype="application/json",
                status_code=500
            )
            return add_cors_headers(error_response)

@app.route(route="reject-request", methods=["GET", "POST", "OPTIONS"])
async def reject_request(req: func.HttpRequest) -> func.HttpResponse:
    """Reject a sales order request"""
    
    if req.method == "OPTIONS":
        response = func.HttpResponse("")
        return add_cors_headers(response)
    
    try:
        # Handle both GET (Teams button) and POST (API) requests
        if req.method == "GET":
            # Teams button click - extract request_id from query parameters
            request_id = req.params.get("request_id", "")
            rejection_reason = "Rejected via Teams notification button"
        else:  # POST request
            body = req.get_json() or {}
            request_id = body.get("request_id", "")
            rejection_reason = body.get("reason", "Rejected via API")
        
        if not request_id or request_id not in approval_requests:
            if req.method == "GET":
                # Return user-friendly HTML page for Teams button click
                html_response = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Sales Order Rejection</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 40px; }}
                        .error {{ color: red; }}
                        .container {{ max-width: 600px; margin: 0 auto; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h2>❌ Sales Order Rejection Error</h2>
                        <p class="error">Request ID '{request_id}' not found or already processed.</p>
                        <p>The request may have expired or been processed already.</p>
                    </div>
                </body>
                </html>
                """
                response = func.HttpResponse(html_response, mimetype="text/html", status_code=404)
                return add_cors_headers(response)
            else:
                error_response = func.HttpResponse(
                    json.dumps({"error": "Invalid request ID"}),
                    mimetype="application/json",
                    status_code=404
                )
                return add_cors_headers(error_response)
        
        # Update approval status to rejected
        approval_requests[request_id]["status"] = "rejected"
        approval_requests[request_id]["rejected_at"] = datetime.now(timezone.utc).isoformat()
        approval_requests[request_id]["rejection_reason"] = rejection_reason
        
        # Send rejection notification
        subject = f"❌ Sales Order Rejected - {request_id}"
        message = f"""
        Your sales order request has been rejected:
        
        Request ID: {request_id}
        Status: REJECTED
        Reason: {rejection_reason}
        
        Please review the request and resubmit if necessary.
        """
        
        # Send notification to requester
        send_notification(approval_requests[request_id].get("created_by", "system"), subject, message)
        
        # Return appropriate response based on request method
        if req.method == "GET":
            # Return user-friendly HTML page for Teams button click
            sales_order_data = approval_requests[request_id]["sales_order_data"]
            html_response = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Sales Order Rejected</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 40px; }}
                    .rejection {{ color: #d73502; }}
                    .container {{ max-width: 600px; margin: 0 auto; }}
                    .details {{ background-color: #f5f5f5; padding: 15px; margin: 20px 0; border-radius: 5px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>❌ Sales Order Rejected</h2>
                    <p class="rejection">The sales order request has been rejected.</p>
                    <div class="details">
                        <h3>Rejection Details:</h3>
                        <p><strong>Request ID:</strong> {request_id}</p>
                        <p><strong>Customer:</strong> {sales_order_data.get('SoldToParty', 'N/A')}</p>
                        <p><strong>Order Type:</strong> {sales_order_data.get('SalesOrderType', 'N/A')}</p>
                        <p><strong>Status:</strong> REJECTED</p>
                        <p><strong>Reason:</strong> {rejection_reason}</p>
                    </div>
                    <p>The requester has been notified. You can close this window.</p>
                </div>
            </body>
            </html>
            """
            response = func.HttpResponse(html_response, mimetype="text/html", status_code=200)
            return add_cors_headers(response)
        else:
            # Return JSON response for API calls
            response_data = {
                "status": "rejected",
                "request_id": request_id,
                "message": "Sales order request rejected",
                "rejection_reason": rejection_reason
            }
            response = func.HttpResponse(json.dumps(response_data), mimetype="application/json")
            return add_cors_headers(response)
            
    except Exception as e:
        logging.exception("[Error] Reject request failed")
        
        if req.method == "GET":
            html_response = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Rejection System Error</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 40px; }}
                    .error {{ color: red; }}
                    .container {{ max-width: 600px; margin: 0 auto; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>❌ System Error</h2>
                    <p class="error">An unexpected error occurred in the rejection system.</p>
                    <p><strong>Error:</strong> {str(e)}</p>
                    <p>Please contact IT support.</p>
                </div>
            </body>
            </html>
            """
            response = func.HttpResponse(html_response, mimetype="text/html", status_code=500)
            return add_cors_headers(response)
        else:
            error_response = func.HttpResponse(
                json.dumps({"error": f"Internal error: {str(e)}"}),
                mimetype="application/json",
                status_code=500
            )
            return add_cors_headers(error_response)

@app.route(route="list-approval-requests", methods=["GET"])
async def list_approval_requests(req: func.HttpRequest) -> func.HttpResponse:
    """List all approval requests"""
    
    if req.method == "OPTIONS":
        response = func.HttpResponse("")
        return add_cors_headers(response)
    
    try:
        # Get requests from both memory and blob storage
        all_requests = list(approval_requests.values())
        
        # Also get requests from blob storage to ensure we have complete data
        blob_requests = await list_approval_requests_from_blob()
        
        # Merge requests, with memory taking precedence (more recent data)
        request_dict = {}
        
        # First add blob storage requests
        for req in blob_requests:
            request_id = req.get("id", "")
            if request_id:
                request_dict[request_id] = req
                
        # Then add/update with memory requests (these are more recent)
        for req in all_requests:
            request_id = req.get("id", "")
            if request_id:
                request_dict[request_id] = req
        
        response_data = {
            "requests": list(request_dict.values()),
            "source": "memory_and_blob_storage",
            "total_count": len(request_dict)
        }
        
        response = func.HttpResponse(
            json.dumps(response_data),
            mimetype="application/json",
            status_code=200
        )
        return add_cors_headers(response)
        
    except Exception as e:
        logging.exception("[Error] List approval requests failed")
        error_response = func.HttpResponse(
            json.dumps({"error": f"Internal error: {str(e)}"}),
            mimetype="application/json",
            status_code=500
        )
        return add_cors_headers(error_response)
