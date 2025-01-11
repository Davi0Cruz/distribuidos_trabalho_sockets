#!/usr/bin/env python3
import socket
import struct
import threading
import time
import json
import random
from datetime import datetime
import device_pb2
import subprocess

class BrightnessSensor:
    def __init__(self):
        # Configurações de rede
        self.MCAST_GRP = '224.0.0.1'
        self.MCAST_PORT = 50000
        self.TCP_PORT = 0  # Será definido dinamicamente
        self.device_type = "brightness_sensor"
        
        # Estado do dispositivo
        self.state = {
            "brightness": 0,
            "unit": "%",
            "update_interval": 2  # segundos
        }
        
        # Inicializar sockets
        self.init_tcp_server()
        self.init_multicast_listener()
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # IP do gateway (será atualizado quando recebermos GATEWAY_DISCOVERY)
        self.gateway_ip = None
        
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
        
    def simulate_brightness(self):
        """Lida com as mudanças de luminosidade e envia dados periodicamente ao Gateway"""
        while True:
            # Testando se a lâmpada está conectada
            pid_ac = subprocess.check_output("ps -aux | grep smart_lamp", shell=True, text=True)
            if len(pid_ac.split("\n")) > 3:
                # Conexão com luminosidade da lâmpada
                with open("files/brightness.txt", "r") as f:
                    conteudo = f.read().split()
                    light = int(conteudo[0])
                    self.state["brightness"] = light
            else:
                with open("files/brightness.txt", "w") as f:
                    f.write("0")
                with open("files/lamp_power.txt", "w") as f:
                    f.write("0")
                self.state["brightness"] = 0
            
            if self.gateway_ip:
                # Cria mensagem de dados do sensor
                sensor_data = device_pb2.SensorData()
                sensor_data.device_id = f"{self.device_type}_{self.get_local_ip()}_{self.TCP_PORT}"
                sensor_data.sensor_type = "brightness"
                sensor_data.value = self.state["brightness"]
                sensor_data.unit = self.state["unit"]
                sensor_data.timestamp = int(time.time())
                
                # Envia para o gateway via UDP
                try:
                    data = sensor_data.SerializeToString()
                    self.udp_socket.sendto(data, (self.gateway_ip, 50002))
                except Exception as e:
                    print(f"Error sending sensor data: {e}")
            
            time.sleep(self.state["update_interval"])
            
    def handle_command(self, command_msg):
        """Processa comandos recebidos (via TCP)"""
        try:
            command = command_msg.command
            params = json.loads(command_msg.parameters) if command_msg.parameters else {}
            
            response = device_pb2.DeviceResponse()
            
            if command == "GET_STATUS":
                response.success = True
                response.message = "Status retrieved"
                response.status = json.dumps(self.state)
                response.attributes["brightness"] = str(self.state["brightness"])
                response.attributes["unit"] = self.state["unit"]

            elif command == "SET_INTERVAL":
                if "interval" in params:
                    interval = int(params["interval"])
                    if 1 <= interval <= 3600:
                        self.state["update_interval"] = interval
                        response.success = True
                        response.message = f"Update interval set to {interval} seconds"
                    else:
                        response.success = False
                        response.message = "Interval must be between 1 and 3600 seconds"
                else:
                    response.success = False
                    response.message = "Missing interval parameter"

            else:
                response.success = False
                response.message = "Unknown command"
            
            return response

        except Exception as e:
            # Em caso de erro ao processar o comando
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
                
                # Recebe mensagem do dispositivo
                data = client_socket.recv(msg_size)
                if not data:
                    break
                    
                # Processa comando
                command_msg = device_pb2.DeviceCommand()
                command_msg.ParseFromString(data)
                
                # Gera resposta
                response = self.handle_command(command_msg)
                
                # Envia resposta de volta
                response_data = response.SerializeToString()
                client_socket.send(len(response_data).to_bytes(4, byteorder='big'))
                client_socket.send(response_data)

        except Exception as e:
            print(f"Error handling TCP client: {e}")
        finally:
            client_socket.close()
            
    def listen_for_discovery(self):
        """Escuta por mensagens de descoberta (multicast) e responde ao Gateway"""
        while True:
            data, addr = self.mcast_socket.recvfrom(1024)
            msg = device_pb2.DeviceCommand()
            msg.ParseFromString(data)
            if msg.command == "GATEWAY_DISCOVERY":
                self.gateway_ip = addr[0]  # Salva IP do gateway para envio de dados
                
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
                
    def run(self):
        """Inicia o dispositivo (sensor)"""
        # Thread para descoberta
        discovery_thread = threading.Thread(target=self.listen_for_discovery)
        discovery_thread.daemon = True
        discovery_thread.start()
        
        # Thread para simulação de luminosidade
        sensor_thread = threading.Thread(target=self.simulate_brightness)
        sensor_thread.daemon = True
        sensor_thread.start()
        
        print(f"Brightness Sensor running on port {self.TCP_PORT}")
        
        # Aceita conexões TCP
        while True:
            client_sock, addr = self.tcp_socket.accept()
            client_thread = threading.Thread(target=self.handle_tcp_client, args=(client_sock, addr))
            client_thread.daemon = True
            client_thread.start()


if __name__ == "__main__":
    sensor = BrightnessSensor()
    sensor.run()
