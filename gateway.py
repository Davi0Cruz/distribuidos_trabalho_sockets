#!/usr/bin/env python3
import socket
import threading
import time
import json
import device_pb2

class Gateway:
    def __init__(self):
        self.MCAST_GRP = '224.0.0.1'
        self.MCAST_PORT = 50000
        self.TCP_PORT = 6000
        
        self.devices = {}  # device_id -> device_info

        self.init_tcp_server()
        self.init_udp_receiver()
        self.init_sensor_receiver()

    def init_tcp_server(self):
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_socket.bind(('0.0.0.0', self.TCP_PORT))
        self.tcp_socket.listen(5)

    def init_udp_receiver(self):
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind(('0.0.0.0', 50001))

    def init_sensor_receiver(self):
        self.sensor_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sensor_socket.bind(('0.0.0.0', 50002))

    def send_discovery_message(self):
        self.devices.clear()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        discovery_msg = device_pb2.DeviceCommand()
        discovery_msg.command = "GATEWAY_DISCOVERY"
        data = discovery_msg.SerializeToString()
        sock.sendto(data, (self.MCAST_GRP, self.MCAST_PORT))
        sock.close()

    def listen_for_device_announcements(self):
        while True:
            data, addr = self.udp_socket.recvfrom(1024)
            discovery_msg = device_pb2.DeviceDiscovery()
            discovery_msg.ParseFromString(data)

            device_id = f"{discovery_msg.device_type}_{discovery_msg.ip}_{discovery_msg.port}"
            device_info = {
                'id': device_id,
                'type': discovery_msg.device_type,
                'ip': discovery_msg.ip,
                'port': discovery_msg.port,
                # Armazena o status fornecido (já deve ser JSON)
                'status': discovery_msg.status if discovery_msg.status else "{}",
                'last_seen': time.time()
            }

            self.devices[device_id] = device_info
            print(f"[Gateway] Device discovered/updated: {device_id}")

    def listen_for_sensor_data(self):
        while True:
            data, addr = self.sensor_socket.recvfrom(2048)
            sensor_data = device_pb2.SensorData()
            sensor_data.ParseFromString(data)

            device_id = sensor_data.device_id
            if device_id not in self.devices:
                self.devices[device_id] = {
                    'id': device_id,
                    'type': sensor_data.sensor_type,
                    'ip': addr[0],
                    'port': 0,
                    'status': "{}",
                    'last_seen': time.time()
                }

            device = self.devices[device_id]
            device['last_seen'] = time.time()

            # Se sensor_data.unit contém o JSON do estado, use isso
            try:
                # Tenta decodificar o 'unit' como JSON
                if sensor_data.unit:
                    json.loads(sensor_data.unit)  # Se não der erro, é um JSON válido
                    device['status'] = sensor_data.unit
            except:
                pass

            # (Opcional) Se quiser armazenar sensor_data.value em 'last_sensor_data':
            device['last_sensor_data'] = {
                'value': sensor_data.value,
                'timestamp': sensor_data.timestamp
            }

            print(f"[Gateway] Sensor data from {device_id}, type={sensor_data.sensor_type}")

    def send_command_to_device(self, device_id, command, parameters=None):
        if device_id not in self.devices:
            return False, "Device not found"

        device = self.devices[device_id]
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((device['ip'], device['port']))

            command_msg = device_pb2.DeviceCommand()
            command_msg.command = command
            if parameters:
                command_msg.parameters = json.dumps(parameters)

            data = command_msg.SerializeToString()
            sock.send(len(data).to_bytes(4, byteorder='big'))
            sock.send(data)

            size_data = sock.recv(4)
            if not size_data:
                return False, "No response from device"

            msg_size = int.from_bytes(size_data, byteorder='big')
            response_data = sock.recv(msg_size)

            response = device_pb2.DeviceResponse()
            response.ParseFromString(response_data)

            # Se o device nos mandou status, atualize
            if response.success and response.status:
                # response.status deve ser JSON completo
                device['status'] = response.status

            return response.success, response.message

        except Exception as e:
            return False, f"Error communicating with device: {e}"
        finally:
            sock.close()

    def handle_client_request(self, client_socket):
        try:
            while True:
                size_data = client_socket.recv(4)
                if not size_data:
                    break
                msg_size = int.from_bytes(size_data, byteorder='big')
                data = client_socket.recv(msg_size)
                if not data:
                    break

                request = device_pb2.ClientRequest()
                request.ParseFromString(data)

                response = device_pb2.ClientResponse()

                if request.command == "LIST_DEVICES":
                    response.success = True
                    response.message = "Devices retrieved successfully"
                    for device_info in self.devices.values():
                        dev = response.devices.add()
                        dev.device_id = device_info['id']
                        dev.device_type = device_info['type']
                        dev.ip = device_info['ip']
                        dev.port = device_info['port']
                        dev.status = device_info['status']  # já é JSON
                        if 'last_sensor_data' in device_info:
                            dev.attributes['sensor_data'] = json.dumps(device_info['last_sensor_data'])

                elif request.command == "CONTROL_DEVICE":
                    if not request.device_id:
                        response.success = False
                        response.message = "Missing device_id"
                    else:
                        success, message = self.send_command_to_device(
                            request.device_id,
                            request.action,
                            json.loads(request.parameters) if request.parameters else None
                        )
                        response.success = success
                        response.message = message

                elif request.command == "SET_STATUS":
                    if not request.device_id:
                        response.success = False
                        response.message = "Missing device_id"
                    else:
                        success, message = self.send_command_to_device(request.device_id, "GET_STATUS")
                        response.success = success
                        response.message = message

                else:
                    response.success = False
                    response.message = "Unknown command"

                response_data = response.SerializeToString()
                client_socket.send(len(response_data).to_bytes(4, byteorder='big'))
                client_socket.send(response_data)

        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            client_socket.close()

    def run(self):
        # Threads para receber anúncios e sensor data
        discovery_thread = threading.Thread(target=self.listen_for_device_announcements, daemon=True)
        discovery_thread.start()

        sensor_thread = threading.Thread(target=self.listen_for_sensor_data, daemon=True)
        sensor_thread.start()

        # Envia multicast inicial
        self.send_discovery_message()

        # Periodic discovery
        def periodic_discovery():
            while True:
                time.sleep(15)
                self.send_discovery_message()

        discovery_timer = threading.Thread(target=periodic_discovery, daemon=True)
        discovery_timer.start()

        print(f"Gateway running on port {self.TCP_PORT}")
        while True:
            client_sock, addr = self.tcp_socket.accept()
            t = threading.Thread(target=self.handle_client_request, args=(client_sock,), daemon=True)
            t.start()

if __name__ == "__main__":
    gateway = Gateway()
    gateway.run()
