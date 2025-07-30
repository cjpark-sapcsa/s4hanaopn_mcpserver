# Copilot Studio S/4HANA Connector Troubleshooting Guide

## Issue: Step 2 shows "Unknown tool:" error

### Root Cause Analysis:
The "Unknown tool:" error in Step 2 typically occurs when:
1. **Tool name parameter is empty or null** - Copilot Studio isn't properly passing the selected tool name
2. **Parameter mapping issue** - The `params.name` field isn't being populated correctly
3. **Method selection issue** - The method might not be set to "tools/call" properly

### Quick Diagnostic Steps:

1. **Verify Method Selection**:
   - Ensure "Method" is set to "tools/call" (not "tools/list")
   - Check that this field is visible and properly selected

2. **Check Tool Name Field**:
   - Verify "Tool Name" dropdown shows: query_s4hana, create_s4hana_entity, check_and_create_sales_orders
   - Ensure a tool is actually selected (not blank)

3. **Validate Entity Selection**:
   - Confirm "Entity Type" dropdown shows all 12 S/4HANA entities
   - Select a specific entity (e.g., "salesorders")

### Test Scenarios:

#### ✅ Working Example - Sales Order Query:
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call", 
  "id": 1,
  "params": {
    "name": "query_s4hana",
    "arguments": {
      "entity": "salesorders",
      "query": "$filter=SoldToParty eq 'USCU_L10'&$top=5"
    }
  }
}
```

#### ❌ Common Error - Missing Tool Name:
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "id": 1, 
  "params": {
    "name": "",  // ← PROBLEM: Empty tool name
    "arguments": {
      "entity": "salesorders"
    }
  }
}
```

### Copilot Studio Configuration Checklist:

- [ ] **OpenAPI Version**: 2.1.0 imported successfully
- [ ] **Method Field**: Shows "tools/call" as default, visible as "important"
- [ ] **Tool Name Field**: Shows dropdown with 3 tool options, visible as "important" 
- [ ] **Tool Arguments**: Shows as expandable object, visible as "important"
- [ ] **Entity Type**: Shows dropdown with 12 entities, visible as "important"
- [ ] **OData Query**: Shows as text field, visible as "important"

### Resolution Steps:

1. **Re-import OpenAPI YAML**:
   - Use the latest version (2.1.0) from the workspace
   - Verify no validation errors during import

2. **Test Step 1 First**:
   - Run "tools/list" method to confirm connectivity
   - Verify it returns 3 tools with proper schemas

3. **Manually Set Parameters**:
   - Method: "tools/call"
   - Tool Name: "query_s4hana" 
   - Entity Type: "salesorders"
   - OData Query: "$top=5"

4. **Check Raw Request**:
   - Use browser dev tools to inspect the actual JSON being sent
   - Verify the `params.name` field is populated

### MCP Server Validation:

The MCP server is working correctly as confirmed by direct testing:
- ✅ tools/list returns proper tool definitions
- ✅ tools/call with query_s4hana executes successfully  
- ✅ Returns proper JSON-RPC 2.0 responses
- ✅ S/4HANA connectivity is functional

### Contact Information:
If issues persist after following this guide:
- Check Azure Function logs for any backend errors
- Verify APIM subscription key is valid: `2fba858f7d5444a09026459ec4f83bda`
- Test direct API calls using PowerShell scripts in the workspace
