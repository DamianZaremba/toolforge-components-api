# Toolforge Components API

This is the Toolforge components-api.

For now, it is just a skeleton FastAPI application.

To deploy it, follow the same pattern as the other Toolforge components (jobs-api, envvars-api...)

For local development, you can use the following command to start the application:

```bash
poetry run uvicorn --factory components.main:create_app --workers=2 --reload
```

This will start the application on <http://localhost:8000>.

## API Endpoints

The API provides the following endpoints:

### Tool Configuration

- `GET /v1/tool/{toolname}/config`: Retrieve the configuration for a specific tool.
- `POST /v1/tool/{toolname}/config`: Update the configuration for a specific tool.

### Deployments

- `POST /v1/tool/{toolname}/deploy`: Create a new deployment for a specific tool.
- `GET /v1/tool/{toolname}/deploy/{deploy_id}`: Retrieve information about a specific deployment.

All endpoints are prefixed with `/v1` to ensure versioning of the API.

For detailed information about request and response formats, please refer to the API documentation or the OpenAPI specification.
