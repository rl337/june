# june-grpc-api

Shared gRPC API for June services.

- Source of truth: proto files in `proto/`
- Generated Python stubs are built at install/build time and NOT checked in

Build locally:

```
python -m pip install --upgrade build grpcio-tools
python -m grpc_tools.protoc -I proto --python_out=june_grpc_api --grpc_python_out=june_grpc_api proto/*.proto
python -m build
```

Install from source (will use pre-generated stubs if present):
```
pip install dist/*.whl
```

In services, import as:
```
from june_grpc_api import asr_pb2, asr_pb2_grpc
```


