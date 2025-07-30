# S/4HANA On-Premises MCP Server

S/4HANA On-Premises MCP Server for Business Partner and Sales Order operations with intelligent workflow automation.

## Overview

This MCP (Model Context Protocol) server provides integration with SAP S/4HANA On-Premises systems, enabling AI assistants to interact with Business Partner and Sales Order data through standardized OData APIs.

## Features

- **Business Partner Management**: Query and manage business partner data
- **Sales Order Operations**: Create, query, and manage sales orders
- **Intelligent Workflows**: Automated business processes with AI-driven decision making
- **Azure Functions Deployment**: Serverless architecture for scalability
- **MCP Protocol Support**: Compatible with Claude Desktop and other MCP clients

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│   AI Assistant  │    │   Azure APIM     │    │   S/4HANA System   │
│   (Claude/etc)  │◄──►│   MCP Server     │◄──►│   OData APIs       │
│                 │    │   (Functions)    │    │                     │
└─────────────────┘    └──────────────────┘    └─────────────────────┘
```

## Prerequisites

- Python 3.11+
- Azure Functions Core Tools
- SAP S/4HANA system with OData services enabled
- Azure subscription (for deployment)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/cjpark-sapcsa/s4hanaopn_mcpserver.git
cd s4hanaopn_mcpserver
```

2. Create virtual environment:
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

1. Copy `local.settings.json.template` to `local.settings.json`
2. Update the configuration:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "SAP_BASE_URL": "http://your-s4hana-server:port",
    "SAP_USER": "your-sap-username",
    "SAP_PASS": "your-sap-password"
  }
}
```

## Available Tools

### Query Tools
- `query_s4hana`: Query S/4HANA entities with OData parameters
- `get_pending_so_requests`: Get pending sales order approval requests

### Create Tools  
- `create_s4hana_entity`: Create new entities in S/4HANA
- `create_so_request`: Create sales order request for approval

### Workflow Tools
- `check_and_create_sales_orders`: Automated sales order workflow
- `approve_so_request`: Approve pending sales order requests
- `reject_so_request`: Reject sales order requests

## Usage Examples

### Query Sales Orders
```python
# Query recent sales orders
response = await query_s4hana(
    entity="salesorders",
    query="$top=10&$orderby=CreationDate desc"
)
```

### Create Sales Order Request
```python
# Create approval request
response = await create_so_request(
    customer_id="10100001",
    order_details={
        "SalesOrderType": "OR",
        "SoldToParty": "10100001",
        "PurchaseOrderByCustomer": "PO-2024-001"
    },
    requestor="sales.rep@company.com",
    business_justification="Urgent customer requirement"
)
```

## Deployment

### Local Development
```bash
func start
```

### Azure Deployment
```bash
func azure functionapp publish your-function-app-name
```

## API Endpoints

- **SSE Endpoint**: `/api/sse` - Server-Sent Events for MCP communication
- **Health Check**: `/api/health` - Service health status
- **Tools Discovery**: `/api/tools` - Available MCP tools

## Supported S/4HANA Entities

### Business Partner API
- `businesspartners` - Business partner master data
- `businesspartneraddresses` - Partner addresses
- `businesspartnercontacts` - Partner contacts
- `customers` - Customer data
- `suppliers` - Supplier data

### Sales Order API
- `salesorders` - Sales order headers
- `salesorderitems` - Sales order line items
- `salesorderheaderpartners` - Header partner data
- `salesorderitempartners` - Item partner data
- `salesorderschedulelines` - Schedule lines
- `salesordertexts` - Header texts
- `salesorderitemtexts` - Item texts

## Security

- Azure AD authentication supported
- Subscription key authentication via Azure APIM
- Environment variable configuration for sensitive data
- Network security through Azure private endpoints

## Monitoring

- Application Insights integration
- Azure Monitor metrics
- Custom logging and telemetry
- Health check endpoints

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For support and questions:
- Create an issue on GitHub
- Contact: Microsoft Cloud AI Platform team

## Changelog

### v1.0.0
- Initial release
- Basic S/4HANA integration
- MCP protocol support
- Azure Functions deployment
