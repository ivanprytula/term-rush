import os

# Ephemeral port: each TestClient(app) starts its own gRPC server via lifespan;
# a fixed port would collide across tests (and with a real container already
# running locally). Must be set before content_service.api.config imports.
os.environ.setdefault("GRPC_PORT", "0")
