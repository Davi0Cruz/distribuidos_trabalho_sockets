#!/usr/bin/env python3
import socket
import struct
import threading
import time
import json
from datetime import datetime
import random  # caso queira simular algo
import device_pb2


class AirConditioner:
    def __init__(self):
        # Configurações de rede
        self.MCAST_GRP = '224.0.0.1'
        self.MCAST_PORT = 50000
        self.TCP_PORT = 0  # Será definido dinamicamente
        self.device_type = "air_conditioner"

        # Guardar IP do gateway quando receber GATEWAY_DISCOVERY
        self.gateway_ip = None

        # Temperatura padrão
        self.const_temp = 25

        # Potência padrão
        self.power = 1000

        # Estado do dispositivo
        self.state = {
            "power": "OFF",
            "temperature": self.const_temp,   # temperatura alvo
            "mode": "COOL",     # COOL, HEAT, FAN
            "fan_speed": "AUTO" # LOW, MEDIUM, HIGH, AUTO
        }

        # Atualizando files do sensor de temperatura
        with open("files/temperature.txt", "w") as f:
            f.write(str(self.const_temp))
        with open("files/ac_power.txt", "w") as f:
            f.write("0")

        # Sockets
        self.init_tcp_server()
        self.init_multicast_listener()
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def init_tcp_server(self):
        """Inicializa o servidor TCP para comandos"""
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.bind(('0.0.0.0', 0))
        self.TCP_PORT = self.tcp_socket.getsockname()[1]
        self.tcp_socket.listen(5)

    def init_multicast_listener(self):
        """Inicializa o listener multicast"""
        self.mcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.mcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.mcast_socket.bind(('0.0.0.0', self.MCAST_PORT))

        mreq = struct.pack("4sl", socket.inet_aton(self.MCAST_GRP), socket.INADDR_ANY)
        self.mcast_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    def get_local_ip(self):
        """Obtém o IP local do dispositivo"""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    def handle_command(self, command_msg):
        """Processa comandos recebidos"""
        try:
            command = command_msg.command
            params = json.loads(command_msg.parameters) if command_msg.parameters else {}

            response = device_pb2.DeviceResponse()

            if command == "ON":
                self.state["power"] = "ON"
                self.state["temperature"] = self.const_temp
                with open("files/temperature.txt", "w") as f:
                    f.write(str(self.const_temp))
                with open("files/ac_power.txt", "w") as f:
                    f.write(str(self.power))
                response.success = True
                response.message = "Air conditioner turned on"

            elif command == "OFF":
                self.state["power"] = "OFF"
                self.state["temperature"] = self.const_temp
                with open("files/temperature.txt", "w") as f:
                    f.write(str(self.const_temp))
                with open("files/ac_power.txt", "w") as f:
                    f.write("0")
                response.success = True
                response.message = "Air conditioner turned off"

            elif command == "SET_TEMPERATURE":
                if "temperature" in params:
                    temp = int(params["temperature"])
                    if 16 <= temp <= 30:
                        self.state["power"] = "ON"
                        self.state["temperature"] = temp
                        with open("files/temperature.txt", "w") as f:
                            f.write(str(temp))
                        with open("files/ac_power.txt", "w") as f:
                            f.write(str(self.power))
                        response.success = True
                        response.message = f"Temperature set to {temp}°C"
                    else:
                        response.success = False
                        response.message = "Temperature must be between 16 and 30°C"
                else:
                    response.success = False
                    response.message = "Missing temperature parameter"

            elif command == "SET_MODE":
                if "mode" in params:
                    mode = params["mode"].upper()
                    if mode in ["COOL", "HEAT", "FAN"]:
                        self.state["mode"] = mode
                        response.success = True
                        response.message = f"Mode set to {mode}"
                    else:
                        response.success = False
                        response.message = "Invalid mode"
                else:
                    response.success = False
                    response.message = "Missing mode parameter"

            elif command == "SET_FAN_SPEED":
                if "fan_speed" in params:
                    speed = params["fan_speed"].upper()
                    if speed in ["LOW", "MEDIUM", "HIGH", "AUTO"]:
                        self.state["fan_speed"] = speed
                        response.success = True
                        response.message = f"Fan speed set to {speed}"
                    else:
                        response.success = False
                        response.message = "Invalid fan speed"
                else:
                    response.success = False
                    response.message = "Missing fan_speed parameter"

            elif command == "GET_STATUS":
                response.success = True
                response.message = "Status retrieved"

            else:
                response.success = False
                response.message = "Unknown command"

            response.status = json.dumps(self.state)

            # Passa todos os atributos do estado para o map 'attributes'
            for key, value in self.state.items():
                response.attributes[key] = str(value)

            return response

        except Exception as e:
            response = device_pb2.DeviceResponse()
            response.success = False
            response.message = f"Error: {str(e)}"
            response.status = json.dumps(self.state)
            return response

    def handle_tcp_client(self, client_socket, addr):
        """Gerencia conexões TCP"""
        try:
            while True:
                # Recebe tamanho da mensagem
                size_data = client_socket.recv(4)
                if not size_data:
                    break

                msg_size = int.from_bytes(size_data, byteorder='big')

                # Recebe mensagem
                data = client_socket.recv(msg_size)
                if not data:
                    break

                # Processa comando
                command_msg = device_pb2.DeviceCommand()
                command_msg.ParseFromString(data)

                # Gera resposta
                response = self.handle_command(command_msg)

                # Envia resposta
                response_data = response.SerializeToString()
                client_socket.send(len(response_data).to_bytes(4, byteorder='big'))
                client_socket.send(response_data)

        except Exception as e:
            print(f"Error handling TCP client: {e}")
        finally:
            client_socket.close()

    def listen_for_discovery(self):
        """Escuta por mensagens de descoberta (multicast)"""
        while True:
            data, addr = self.mcast_socket.recvfrom(1024)
            msg = device_pb2.DeviceCommand()
            msg.ParseFromString(data)
            if msg.command == "GATEWAY_DISCOVERY":
                # Salva IP do Gateway para envio periódico
                self.gateway_ip = addr[0]

                # Prepara resposta
                discovery_msg = device_pb2.DeviceDiscovery()
                discovery_msg.device_type = self.device_type
                discovery_msg.ip = self.get_local_ip()
                discovery_msg.port = self.TCP_PORT
                discovery_msg.status = json.dumps(self.state)

                # Envia resposta unicast
                response_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                response_socket.sendto(discovery_msg.SerializeToString(), (addr[0], 50001))
                response_socket.close()

    def periodically_send_state(self):
        """Envia periodicamente o estado via UDP para o gateway"""
        while True:
            # Só envia se souber o IP do gateway
            if self.gateway_ip is not None:
                try:
                    sensor_data = device_pb2.SensorData()
                    sensor_data.device_id = f"{self.device_type}_{self.get_local_ip()}_{self.TCP_PORT}"
                    sensor_data.sensor_type = "ac_state"
                    # Podemos colocar alguma informação numérica em 'value', por exemplo a temperatura
                    sensor_data.value = float(self.state.get("temperature", self.const_temp))
                    sensor_data.unit = json.dumps(self.state)  # 'label' indicando que o state em si está em attributes
                    sensor_data.timestamp = int(time.time())

                    # Se quisermos mandar o estado inteiro em JSON, podemos usar attributes no gateway
                    # Mas o SensorData não tem attributes. Então aqui vai uma "gambiarra":
                    # Podemos converter para JSON e colocar no campo 'unit' ou criar outro proto. 
                    # Vou demonstrar guardando no 'unit' e ajustando o Gateway para interpretar:
                    # (Exemplo: sensor_data.unit = json.dumps(self.state) ... mas perderíamos a info 'json_state')
                    # Então farei outro hack: mandar no 'unit' a string "json_state", e mandar de fato no 'value' a temp
                    # e no gateway iremos armazenar isso. Se quiser, pode criar outro message. 

                    # Envia para porta 50002, que no gateway está escutando sensor_data
                    data = sensor_data.SerializeToString()
                    self.udp_socket.sendto(data, (self.gateway_ip, 50002))
                except Exception as e:
                    print(f"[AC] Error sending periodic state: {e}")

            time.sleep(15)  # ajusta o intervalo desejado

    def run(self):
        """Inicia o dispositivo"""
        # Thread para descoberta
        discovery_thread = threading.Thread(target=self.listen_for_discovery, daemon=True)
        discovery_thread.start()

        # Thread para envio periódico de estado
        periodic_thread = threading.Thread(target=self.periodically_send_state, daemon=True)
        periodic_thread.start()

        print(f"Air Conditioner running on port {self.TCP_PORT}")

        # Aceita conexões TCP
        while True:
            client_sock, addr = self.tcp_socket.accept()
            client_thread = threading.Thread(target=self.handle_tcp_client, args=(client_sock, addr), daemon=True)
            client_thread.start()


if __name__ == "__main__":
    ac = AirConditioner()
    ac.run()
