# distribuidos_trabalho_sockets
Essa linha precisa ser rodada apenas na primeira vez que for rodar o projeto ou se fizer alguma mudança em device.proto. Ela gera automaticamente o arquivo device_pb2.py
* protoc --python_out=. device.proto

Para rodar o projeto rode essas linhas em terminais diferentes.
* python3 gateway.py
* python3 air_conditioner.py
* python3 smart_lamp.py
* python3 temperature_sensor.py
* python3 client.py
* python3 client_gui.py

Em seguida clique em Conectar e depois selecione o smart device e clique em configurações avançadas
