#!/usr/bin/env python3
import socket
import struct
import threading
import time
import json
import device_pb2
import subprocess


class TemperatureSensor:
    def __init__(self):
        # Configurações de rede
        self.MCAST_GRP = '224.0.0.1'
        self.MCAST_PORT = 50000
        self.TCP_PORT = 0  # Será definido dinamicamente
        self.device_type = "temperature_sensor"
        
        # Estado do dispositivo (aqui consideramos "25°C" como ambiente inicial)
        self.state = {
            "temperature": 25.0,
            "unit": "°C",
            "update_interval": 2  # segundos (ex.: a cada 2s)
        }

        # Temperatura que consideramos "externa/neutra"
        self.default_temp = 25.0

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
    
    def simulate_environment_temperature(self):
        """
        Ajusta a temperatura do ambiente de forma 'aproximada',
        considerando o estado do ar-condicionado e da lâmpada.
        """

        # -----------------------------
        # Ler arquivos do AC
        # -----------------------------
        pid_ac = subprocess.check_output("ps -aux | grep air_conditioner.py", shell=True, text=True)
        if len(pid_ac.split("\n")) > 3:
            try:
                with open("files/ac_power.txt", "r") as f:
                    ac_power_val = int(f.read().strip())  # se > 0 -> ON, se ==0 -> OFF

                with open("files/ac_settemp.txt", "r") as f:
                    ac_set_temp = float(f.read().strip())  # 16..30

                with open("files/ac_mode.txt", "r") as f:
                    ac_mode = f.read().strip()  # COOL, HEAT, FAN

                with open("files/ac_fanspeed.txt", "r") as f:
                    ac_fan_speed = f.read().strip()  # LOW, MEDIUM, HIGH, AUTO
            except:
                # Se der algum erro de leitura, assumimos valores padrão
                ac_power_val = 0
                ac_set_temp = 25.0
                ac_mode = "COOL"
                ac_fan_speed = "AUTO"
        else:
            # Se o ar condicionado não estiver funcionando, assumimos valores padrão
            ac_power_val = 0
            ac_set_temp = 25.0
            ac_mode = "COOL"
            ac_fan_speed = "AUTO"
      
        # A temperatura atual do ambiente
        current_temp = self.state["temperature"]

        # -----------------------------
        # Cálculos de influência
        # -----------------------------
        # 1) efeito natural de "voltar" para a default_temp
        #    se nada estiver ligado (ou dependendo do caso)
        #    iremos "aproximar" do default_temp vagarosamente
        #    Exemplo: delta ~ (default_temp - current_temp) * 0.01
        #    => se current_temp < default_temp, sobe lentamente, e vice-versa
        approach_rate = 0.02  # quão rápido volta à temp default
        delta = (self.default_temp - current_temp) * approach_rate

        # 2) efeito do ar-condicionado
        #    - se ac_power_val > 0 => AC está ON
        #      COOL -> tende a abaixar
        #      HEAT -> tende a aumentar
        #      FAN  -> efeito menor
        #    - intensidade depende do fan_speed
        fan_factor = {
            "LOW": 0.5,
            "MEDIUM": 1.0,
            "HIGH": 1.5,
            "AUTO": 1.0
        }.get(ac_fan_speed, 1.0)

        ac_effect = 0.0
        if ac_power_val > 0:
            if ac_mode == "COOL":
                # Podemos diminuir a temp para se aproximar de ac_set_temp
                # Exemplo de variação inversamente proporcional à diferença
                # ou um valor fixo. Aqui, uso algo simples:
                if current_temp > ac_set_temp:
                    # resfriar
                    ac_effect = -0.2 * fan_factor  # resfriamento base
                else:
                    # se já está abaixo do set_temp, não esfria mais
                    ac_effect = 0.0

            elif ac_mode == "HEAT":
                if current_temp < ac_set_temp:
                    # aquecer
                    ac_effect = +0.2 * fan_factor
                else:
                    ac_effect = 0.0

            elif ac_mode == "FAN":
                # Modo FAN não muda muito a temp
                # mas se a temp estiver abaixo do default, poderia subir um pouco
                # ou se estiver acima, poderia descer um pouco.
                # Aqui faremos um pequeno "empurrão" para se aproximar do default_temp
                ac_effect = 0.05 * fan_factor * (self.default_temp - current_temp)

        # -----------------------------
        # Soma tudo
        # -----------------------------
        new_temp = current_temp + delta + ac_effect

        # Podemos limitar para um range mínimo/máximo
        if new_temp < 5:
            new_temp = 5
        if new_temp > 40:
            new_temp = 40

        # Atualiza no estado
        self.state["temperature"] = new_temp

        # Apenas para fácil conferência externa
        with open("files/environment_temp.txt", "w") as f:
            f.write(f"{new_temp:.2f}")

    def simulate_temperature(self):
        """Lida com a simulação de temperatura e envia dados periodicamente ao Gateway"""
        while True:
            self.simulate_environment_temperature()

            # Agora, envia (via UDP) a temperatura para o Gateway
            if self.gateway_ip:
                sensor_data = device_pb2.SensorData()
                sensor_data.device_id = f"{self.device_type}_{self.get_local_ip()}_{self.TCP_PORT}"
                sensor_data.sensor_type = "temperature"
                sensor_data.value = self.state["temperature"]
                sensor_data.unit = self.state["unit"]
                sensor_data.timestamp = int(time.time())
                
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
                # Retornamos status em JSON
                response.status = json.dumps(self.state)
                response.attributes["temperature"] = str(self.state["temperature"])
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

            if not response.status:
                response.status = json.dumps(self.state)
            
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
                size_data = client_socket.recv(4)
                if not size_data:
                    break
                    
                msg_size = int.from_bytes(size_data, byteorder='big')
                data = client_socket.recv(msg_size)
                if not data:
                    break
                    
                command_msg = device_pb2.DeviceCommand()
                command_msg.ParseFromString(data)
                
                response = self.handle_command(command_msg)
                
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
                self.gateway_ip = addr[0]  # Salva IP do gateway
                
                discovery_msg = device_pb2.DeviceDiscovery()
                discovery_msg.device_type = self.device_type
                discovery_msg.ip = self.get_local_ip()
                discovery_msg.port = self.TCP_PORT
                discovery_msg.status = json.dumps(self.state)
                
                response_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                response_socket.sendto(discovery_msg.SerializeToString(), (addr[0], 50001))
                response_socket.close()
                
    def run(self):
        discovery_thread = threading.Thread(target=self.listen_for_discovery)
        discovery_thread.daemon = True
        discovery_thread.start()
        
        sensor_thread = threading.Thread(target=self.simulate_temperature)
        sensor_thread.daemon = True
        sensor_thread.start()
        
        print(f"Temperature Sensor running on port {self.TCP_PORT}")
        
        while True:
            client_sock, addr = self.tcp_socket.accept()
            client_thread = threading.Thread(target=self.handle_tcp_client, args=(client_sock, addr))
            client_thread.daemon = True
            client_thread.start()


if __name__ == "__main__":
    sensor = TemperatureSensor()
    sensor.run()
