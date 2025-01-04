#!/usr/bin/env python3
import socket
import struct
import threading
import time
import json
from datetime import datetime
import device_pb2


class SmartLamp:
    def __init__(self):
        # Configurações de rede
        self.MCAST_GRP = '224.0.0.1'
        self.MCAST_PORT = 50000
        self.TCP_PORT = 0  # Será definido dinamicamente
        self.device_type = "smart_lamp"

        # Guardar IP do gateway quando receber GATEWAY_DISCOVERY
        self.gateway_ip = None

        # Estado do dispositivo
        self.state = {
            "power": "OFF",
            "brightness": 50  # 0-100
        }

        # Inicializar sockets
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
                response.success = True
                response.message = "Lamp turned on"

            elif command == "OFF":
                self.state["power"] = "OFF"
                response.success = True
                response.message = "Lamp turned off"

            elif command == "SET_BRIGHTNESS":
                if "brightness" in params:
                    brightness = int(params["brightness"])
                    if 0 <= brightness <= 100:
                        self.state["brightness"] = brightness
                        response.success = True
                        response.message = f"Brightness set to {brightness}%"
                    else:
                        response.success = False
                        response.message = "Brightness must be between 0 and 100"
                else:
                    response.success = False
                    response.message = "Missing brightness parameter"

            elif command == "GET_STATUS":
                response.success = True
                response.message = "Status retrieved"

            else:
                response.success = False
                response.message = "Unknown command"

            # Sempre atualiza o status e attributes
            response.status = json.dumps(self.state)
            response.attributes["power"] = self.state["power"]
            response.attributes["brightness"] = str(self.state["brightness"])

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
                # Recebe tamanho da mensagem (4 bytes)
                size_data = client_socket.recv(4)
                if not size_data:
                    break

                msg_size = int.from_bytes(size_data, byteorder='big')

                # Recebe a mensagem do tamanho especificado
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
            if data.decode('utf-8') == "GATEWAY_DISCOVERY":
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
            if self.gateway_ip is not None:
                try:
                    sensor_data = device_pb2.SensorData()
                    sensor_data.device_id = f"{self.device_type}_{self.get_local_ip()}_{self.TCP_PORT}"
                    sensor_data.sensor_type = "lamp_state"
                    # Podemos enviar o brilho como valor numérico
                    sensor_data.value = float(self.state.get("brightness", 50))
                    sensor_data.unit = json.dumps(self.state)  # "indicando" que o resto do estado vem em JSON
                    sensor_data.timestamp = int(time.time())

                    # Envia pro gateway na porta 50002
                    data = sensor_data.SerializeToString()
                    self.udp_socket.sendto(data, (self.gateway_ip, 50002))
                except Exception as e:
                    print(f"[Lamp] Error sending periodic state: {e}")

            time.sleep(15)

    def run(self):
        """Inicia o dispositivo"""
        # Thread para descoberta
        discovery_thread = threading.Thread(target=self.listen_for_discovery, daemon=True)
        discovery_thread.start()

        # Thread para envio periódico
        periodic_thread = threading.Thread(target=self.periodically_send_state, daemon=True)
        periodic_thread.start()

        print(f"Smart Lamp running on port {self.TCP_PORT}")

        # Aceita conexões TCP
        while True:
            client_sock, addr = self.tcp_socket.accept()
            client_thread = threading.Thread(target=self.handle_tcp_client, args=(client_sock, addr), daemon=True)
            client_thread.start()


if __name__ == "__main__":
    lamp = SmartLamp()
    lamp.run()
