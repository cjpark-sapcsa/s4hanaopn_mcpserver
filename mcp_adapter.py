import azure.functions as func
import json
import logging
import httpx
import os
from typing import Optional, Dict, Any

def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    S/4HANA MCP Adapter Function
    Translates simplified Copilot Studio requests to MCP format
    """
    logging.info('S/4HANA MCP Adapter function processed a request.')
    
    # CORS headers
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Ocp-Apim-Subscription-Key'
        return response
    
    # Handle OPTIONS request for CORS
    if req.method == "OPTIONS":
        response = func.HttpResponse("")
        return add_cors_headers(response)
    
    try:
        # Get request body
        req_body = req.get_json()
        if not req_body:
            response = func.HttpResponse(
                json.dumps({"error": "Invalid request body"}),
                status_code=400,
                mimetype="application/json"
            )
            return add_cors_headers(response)
        
        # Extract simplified parameters
        jsonrpc = req_body.get('jsonrpc', '2.0')
        method = req_body.get('method', 'tools/call')
        req_id = req_body.get('id', 1)
        tool_name = req_body.get('tool_name')
        entity = req_body.get('entity')
        query = req_body.get('query')
        payload = req_body.get('payload')
        
        # Handle tools/list method (discovery)
        if method == 'tools/list':
            mcp_request = {
                "jsonrpc": jsonrpc,
                "method": method,
                "id": req_id
            }
        
        # Handle tools/call method (execution)
        elif method == 'tools/call':
            if not tool_name:
                response = func.HttpResponse(
                    json.dumps({
                        "jsonrpc": jsonrpc,
                        "id": req_id,
                        "error": {
                            "code": -32602,
                            "message": "Invalid params: tool_name is required for tools/call"
                        }
                    }),
                    status_code=400,
                    mimetype="application/json"
                )
                return add_cors_headers(response)
            
            # Build arguments based on tool type
            arguments = {}
            if tool_name == 'query_s4hana':
                if entity:
                    arguments['entity'] = entity
                if query:
                    arguments['query'] = query
            elif tool_name == 'create_s4hana_entity':
                if entity:
                    arguments['entity'] = entity
                if payload:
                    arguments['payload'] = payload
            elif tool_name == 'check_and_create_sales_orders':
                if req_body.get('customer_filter'):
                    arguments['customer_filter'] = req_body.get('customer_filter')
                if req_body.get('min_orders'):
                    arguments['min_orders'] = req_body.get('min_orders')
                if req_body.get('line_items_to_create'):
                    arguments['line_items_to_create'] = req_body.get('line_items_to_create')
            
            # Create MCP request
            mcp_request = {
                "jsonrpc": jsonrpc,
                "method": method,
                "id": req_id,
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
        
        else:
            response = func.HttpResponse(
                json.dumps({
                    "jsonrpc": jsonrpc,
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }),
                status_code=400,
                mimetype="application/json"
            )
            return add_cors_headers(response)
        
        # Forward to existing MCP endpoint
        mcp_url = "https://mcp2sapdemo.azure-api.net/s4hana-mcp-v2/sse"
        headers = {
            'Ocp-Apim-Subscription-Key': '2fba858f7d5444a09026459ec4f83bda',
            'Content-Type': 'application/json'
        }
        
        logging.info(f"Forwarding MCP request: {json.dumps(mcp_request)}")
        
        # Make request to MCP server
        with httpx.Client(timeout=30.0) as client:
            mcp_response = client.post(
                mcp_url,
                json=mcp_request,
                headers=headers
            )
            mcp_response.raise_for_status()
            
            # Return the MCP response
            response = func.HttpResponse(
                mcp_response.text,
                status_code=mcp_response.status_code,
                mimetype="application/json"
            )
            return add_cors_headers(response)
    
    except httpx.RequestError as e:
        logging.error(f"Request error: {str(e)}")
        response = func.HttpResponse(
            json.dumps({
                "jsonrpc": "2.0",
                "id": req_body.get('id', 1) if req_body else 1,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }),
            status_code=500,
            mimetype="application/json"
        )
        return add_cors_headers(response)
    
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        response = func.HttpResponse(
            json.dumps({
                "jsonrpc": "2.0",
                "id": req_body.get('id', 1) if req_body else 1,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }),
            status_code=500,
            mimetype="application/json"
        )
        return add_cors_headers(response)
