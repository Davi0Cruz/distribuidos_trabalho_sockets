#!/usr/bin/env python3
import socket
import json
import sys
import device_pb2
from datetime import datetime

class SmartHomeClient:
    def __init__(self, gateway_ip="127.0.0.1", gateway_port=6000):
        self.gateway_ip = gateway_ip
        self.gateway_port = gateway_port
        self.sock = None
        
    def connect(self):
        """Conecta ao gateway"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.gateway_ip, self.gateway_port))
            return True
        except Exception as e:
            print(f"Error connecting to gateway: {e}")
            return False
            
    def disconnect(self):
        """Desconecta do gateway"""
        if self.sock:
            self.sock.close()
            self.sock = None
            
    def send_request(self, request):
        """Envia requisição para o gateway"""
        if not self.sock:
            if not self.connect():
                return None
                
        try:
            # Envia requisição
            data = request.SerializeToString()
            self.sock.send(len(data).to_bytes(4, byteorder='big'))
            self.sock.send(data)
            
            # Recebe resposta
            size_data = self.sock.recv(4)
            if not size_data:
                return None
                
            msg_size = int.from_bytes(size_data, byteorder='big')
            response_data = self.sock.recv(msg_size)
            
            # Processa resposta
            response = device_pb2.ClientResponse()
            response.ParseFromString(response_data)
            return response
            
        except Exception as e:
            print(f"Error communicating with gateway: {e}")
            self.disconnect()
            return None
            
    def list_devices(self):
        """Lista todos os dispositivos"""
        request = device_pb2.ClientRequest()
        request.command = "LIST_DEVICES"
        
        response = self.send_request(request)
        if response and response.success:
            print("\nDispositivos disponíveis:")
            print("-" * 50)
            for device in response.devices:
                print(f"ID: {device.device_id}")
                print(f"Tipo: {device.device_type}")
                print(f"IP: {device.ip}:{device.port}")
                
                try:
                    status = json.loads(device.status)
                    print("Status:")
                    for key, value in status.items():
                        print(f"  {key}: {value}")
                except:
                    print(f"Status: {device.status}")
                    
                if 'sensor_data' in device.attributes:
                    sensor_data = json.loads(device.attributes['sensor_data'])
                    print("Último dado do sensor:")
                    for key, value in sensor_data.items():
                        if key == 'timestamp':
                            print(f"  {key}: {datetime.fromtimestamp(value)}")
                        else:
                            print(f"  {key}: {value}")
                            
                print("-" * 50)
        else:
            print("Erro ao listar dispositivos")
            
    def control_device(self, device_id, action, parameters=None):
        """Envia comando para um dispositivo"""
        request = device_pb2.ClientRequest()
        request.command = "CONTROL_DEVICE"
        request.device_id = device_id
        request.action = action
        if parameters:
            request.parameters = json.dumps(parameters)
            
        response = self.send_request(request)
        if response:
            print(f"Response: {response.message}")
            return response.success
        return False
            
    def get_device_status(self, device_id):
        """Obtém status de um dispositivo"""
        request = device_pb2.ClientRequest()
        request.command = "GET_STATUS"
        request.device_id = device_id
        
        response = self.send_request(request)
        if response:
            print(f"Response: {response.message}")
            return response.success
        return False
        
    def show_menu(self):
        """Mostra menu de opções"""
        print("\nSmart Home Control")
        print("1. Listar dispositivos")
        print("2. Controlar lâmpada")
        print("3. Controlar ar condicionado")
        print("4. Ver status de dispositivo")
        print("0. Sair")
        
    def control_lamp(self):
        """Menu para controle de lâmpada"""
        device_id = input("Digite o ID da lâmpada: ")
        print("\nOpções:")
        print("1. Ligar")
        print("2. Desligar")
        print("3. Ajustar brilho")
        
        option = input("Escolha uma opção: ")
        
        if option == "1":
            self.control_device(device_id, "ON")
        elif option == "2":
            self.control_device(device_id, "OFF")
        elif option == "3":
            brightness = input("Digite o brilho (0-100): ")
            self.control_device(device_id, "SET_BRIGHTNESS", {"brightness": int(brightness)})
            
    def control_ac(self):
        """Menu para controle do ar condicionado"""
        device_id = input("Digite o ID do ar condicionado: ")
        print("\nOpções:")
        print("1. Ligar")
        print("2. Desligar")
        print("3. Ajustar temperatura")
        print("4. Mudar modo")
        print("5. Ajustar velocidade do ventilador")
        
        option = input("Escolha uma opção: ")
        
        if option == "1":
            self.control_device(device_id, "ON")
        elif option == "2":
            self.control_device(device_id, "OFF")
        elif option == "3":
            temp = input("Digite a temperatura (16-30): ")
            self.control_device(device_id, "SET_TEMPERATURE", {"temperature": int(temp)})
        elif option == "4":
            print("Modos disponíveis: COOL, HEAT, FAN")
            mode = input("Digite o modo: ")
            self.control_device(device_id, "SET_MODE", {"mode": mode})
        elif option == "5":
            print("Velocidades disponíveis: LOW, MEDIUM, HIGH, AUTO")
            speed = input("Digite a velocidade: ")
            self.control_device(device_id, "SET_FAN_SPEED", {"fan_speed": speed})
            
    def run(self):
        """Loop principal do cliente"""
        while True:
            self.show_menu()
            option = input("Escolha uma opção: ")
            
            if option == "0":
                break
            elif option == "1":
                self.list_devices()
            elif option == "2":
                self.control_lamp()
            elif option == "3":
                self.control_ac()
            elif option == "4":
                device_id = input("Digite o ID do dispositivo: ")
                self.get_device_status(device_id)
            else:
                print("Opção inválida!")
                
        self.disconnect()

if __name__ == "__main__":
    client = SmartHomeClient()
    client.run()