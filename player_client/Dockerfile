
FROM python

RUN mkdir /service
COPY protobufs/ /service/protobufs/
COPY player_client/ /service/player_client/
WORKDIR /service/player_client
RUN python -m pip install --upgrade pip
RUN python -m pip install --upgrade setuptools
RUN python -m pip install --no-cache-dir  --force-reinstall -Iv grpcio-tools==1.36.1
RUN python -m pip install -r requirements.txt
RUN python -m grpc_tools.protoc -I ../protobufs --python_out=. \
           --grpc_python_out=. ../protobufs/player.proto

EXPOSE 50051
ENTRYPOINT [ "python", "client.py" ]

