import os
from concurrent import futures
import grpc

from june_grpc_api import llm_pb2, llm_pb2_grpc


class PassthroughLLM(llm_pb2_grpc.LLMServiceServicer):
    def Generate(self, request: llm_pb2.GenerateRequest, context) -> llm_pb2.GenerateResponse:
        prompt = request.prompt or ""
        # Passthrough: echo prompt or minimal transformation
        text = f"[passthrough] {prompt}"
        return llm_pb2.GenerateResponse(text=text)

    def HealthCheck(self, request: llm_pb2.HealthRequest, context) -> llm_pb2.HealthResponse:
        return llm_pb2.HealthResponse(healthy=True, model_name="passthrough")


def serve() -> None:
    port = int(os.getenv("LLM_PORT", "50051"))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    llm_pb2_grpc.add_LLMServiceServicer_to_server(PassthroughLLM(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()



