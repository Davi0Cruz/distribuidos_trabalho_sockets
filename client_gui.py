#!/usr/bin/env python3
import socket
import json
from datetime import datetime

import device_pb2

import tkinter as tk
from tkinter import ttk, messagebox

import ttkbootstrap as tb
from ttkbootstrap.constants import *

# ===============================================
#           CLIENTE DE COMUNICAÇÃO
# ===============================================
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
            return True, "Conexão estabelecida com sucesso!"
        except Exception as e:
            return False, f"Erro ao conectar: {e}"
            
    def disconnect(self):
        """Desconecta do gateway"""
        if self.sock:
            self.sock.close()
            self.sock = None

    def is_connected(self):
        return self.sock is not None

    def send_request(self, request):
        """Envia requisição para o gateway e obtém resposta"""
        if not self.sock:
            return None, "Não há conexão com o Gateway."

        try:
            data = request.SerializeToString()
            self.sock.send(len(data).to_bytes(4, byteorder='big'))
            self.sock.send(data)
            
            # Recebe resposta
            size_data = self.sock.recv(4)
            if not size_data:
                return None, "Gateway não retornou dados."
                
            msg_size = int.from_bytes(size_data, byteorder='big')
            response_data = self.sock.recv(msg_size)
            
            # Processa resposta
            response = device_pb2.ClientResponse()
            response.ParseFromString(response_data)
            return response, None
            
        except Exception as e:
            return None, f"Erro no envio/recebimento: {e}"
            
    def list_devices(self):
        """Lista todos os dispositivos (retorna ClientResponse)"""
        request = device_pb2.ClientRequest()
        request.command = "LIST_DEVICES"
        return self.send_request(request)
            
    def control_device(self, device_id, action, parameters=None):
        """Envia comando para um dispositivo"""
        request = device_pb2.ClientRequest()
        request.command = "CONTROL_DEVICE"
        request.device_id = device_id
        request.action = action
        if parameters:
            request.parameters = json.dumps(parameters)
        return self.send_request(request)

    def get_device_status(self, device_id):
        """Obtém status de um dispositivo (retorna ClientResponse)"""
        request = device_pb2.ClientRequest()
        request.command = "GET_STATUS"
        request.device_id = device_id
        return self.send_request(request)


# ===============================================
#       POP-UP COM CONFIGURAÇÕES DO DEVICE
# ===============================================
class DeviceConfigPopup(tb.Toplevel):
    """
    Exibe uma janela pop-up com detalhes do dispositivo
    e permite ajustes em tempo real, exibindo 
    o status completo ao dar "Get Status".
    """
    def __init__(self, parent, client, device_id, device_type):
        super().__init__(parent)
        self.main_app = parent  # para escrever no log principal
        self.title(f"Configurações - {device_id}")
        self.client = client
        self.device_id = device_id
        self.device_type = device_type

        self.geometry("500x420")  # aumentei um pouco para comportar novos campos
        self.minsize(500, 420)

        # Label informativa
        lbl_info = tb.Label(
            self, 
            text=f"Dispositivo: {device_id}\nTipo: {device_type}",
            font="-size 11 -weight bold"
        )
        lbl_info.pack(pady=10)

        # Frame para botões de status/comandos
        frm_cmd = tb.Frame(self)
        frm_cmd.pack(pady=5, fill=X, expand=False)

        # Botão GET STATUS
        btn_status = tb.Button(frm_cmd, text="Get Status", command=self.on_get_status, bootstyle=PRIMARY)
        btn_status.pack(side=LEFT, padx=5)

        # ----------------------------------------
        # Se for Lâmpada
        # ----------------------------------------
        if device_type == "smart_lamp":
            btn_on = tb.Button(frm_cmd, text="Ligar", command=lambda: self.send_cmd("ON"), bootstyle=SUCCESS)
            btn_on.pack(side=LEFT, padx=5)

            btn_off = tb.Button(frm_cmd, text="Desligar", command=lambda: self.send_cmd("OFF"), bootstyle=DANGER)
            btn_off.pack(side=LEFT, padx=5)

            # Slider para brightness
            frm_bri = tb.Frame(self)
            frm_bri.pack(pady=5, fill=X, expand=False)

            tb.Label(frm_bri, text="Brilho (0-100):").pack(side=LEFT, padx=10)
            self.brightness_scale = tb.Scale(
                frm_bri,
                from_=0, to=100,
                orient="horizontal",
                length=200,
                command=self.on_brightness_change,
                bootstyle=INFO
            )
            self.brightness_scale.set(50)  # valor inicial
            self.brightness_scale.pack(side=LEFT)

        # ----------------------------------------
        # Se for Ar-Condicionado
        # ----------------------------------------
        elif device_type == "air_conditioner":
            btn_on = tb.Button(frm_cmd, text="Ligar", command=lambda: self.send_cmd("ON"), bootstyle=SUCCESS)
            btn_on.pack(side=LEFT, padx=5)

            btn_off = tb.Button(frm_cmd, text="Desligar", command=lambda: self.send_cmd("OFF"), bootstyle=DANGER)
            btn_off.pack(side=LEFT, padx=5)

            # Entrada de temperatura
            temp_frame = tb.Frame(self)
            temp_frame.pack(pady=5)
            tb.Label(temp_frame, text="Temperatura (16-30): ").pack(side=LEFT)
            self.temp_entry = tb.Entry(temp_frame, width=4)
            self.temp_entry.pack(side=LEFT, padx=5)
            btn_temp = tb.Button(temp_frame, text="Set Temp", command=self.on_set_temperature, bootstyle=INFO)
            btn_temp.pack(side=LEFT)

            # Seletor de Mode
            mode_frame = tb.Frame(self)
            mode_frame.pack(pady=5)
            tb.Label(mode_frame, text="Mode:").pack(side=LEFT, padx=5)

            self.mode_var = tk.StringVar(value="COOL")
            self.mode_combo = ttk.Combobox(mode_frame, textvariable=self.mode_var, state="readonly")
            self.mode_combo['values'] = ("COOL", "HEAT", "FAN")
            self.mode_combo.pack(side=LEFT, padx=5)

            btn_mode = tb.Button(mode_frame, text="Set Mode", command=self.on_set_mode, bootstyle=INFO)
            btn_mode.pack(side=LEFT, padx=5)

            # Seletor de Fan Speed
            fan_frame = tb.Frame(self)
            fan_frame.pack(pady=5)
            tb.Label(fan_frame, text="Fan Speed:").pack(side=LEFT, padx=5)

            self.fan_var = tk.StringVar(value="AUTO")
            self.fan_combo = ttk.Combobox(fan_frame, textvariable=self.fan_var, state="readonly")
            self.fan_combo['values'] = ("LOW", "MEDIUM", "HIGH", "AUTO")
            self.fan_combo.pack(side=LEFT, padx=5)

            btn_fan = tb.Button(fan_frame, text="Set Fan", command=self.on_set_fan_speed, bootstyle=INFO)
            btn_fan.pack(side=LEFT, padx=5)

        # Caixa de texto para exibir o status
        lbl_st = tb.Label(self, text="Status do Dispositivo:")
        lbl_st.pack(pady=5)

        self.txt_result = tb.Text(self, wrap="word", height=8)
        self.txt_result.pack(fill=BOTH, expand=True, padx=10, pady=5)

        # Barra de rolagem vertical
        scroll_popup = tb.Scrollbar(self, command=self.txt_result.yview)
        scroll_popup.pack(side=RIGHT, fill=Y)
        self.txt_result.configure(yscrollcommand=scroll_popup.set)

    # -------------------------------------
    # Ações e Handlers
    # -------------------------------------
    def on_get_status(self):
        """Busca o status completo do dispositivo e exibe no popup"""
        resp, error = self.client.get_device_status(self.device_id)
        if error:
            self.write_result(f"[ERRO] {error}")
            return
        if not resp:
            self.write_result("[ERRO] Sem resposta do Gateway.")
            return
        if resp.success:
            self.write_result(f"[GET_STATUS] {resp.message}")
            # Se o próprio dispositivo retorna status em JSON, exiba:
            if resp.status:
                self._show_state(resp.status)
        else:
            self.write_result(f"[ERRO] {resp.message}")

    def _show_state(self, status_json_str):
        """Exibe o estado (JSON) no textbox"""
        try:
            state = json.loads(status_json_str)
            self.write_result(">>> Estado atual (JSON):")
            for k, v in state.items():
                self.write_result(f"   {k}: {v}")
        except:
            self.write_result("Erro ao decodificar status JSON.")

    def send_cmd(self, command, params=None):
        """Envia um comando ao dispositivo"""
        self.main_app.write_log(f"Enviando comando '{command}' para {self.device_id}", "[ACTION]")
        resp, error = self.client.control_device(self.device_id, command, params or {})
        if error:
            self.write_result(f"[ERRO] {error}")
            self.main_app.write_log(error, "[ERRO]")
            return
        if not resp:
            self.write_result("[ERRO] Sem resposta do Gateway.")
            self.main_app.write_log("Sem resposta do Gateway.", "[ERRO]")
            return

        self.write_result(f"[{command}] {resp.message}")
        self.main_app.write_log(f"Resposta do device: {resp.message}", "[RESPONSE]")

        # Se o device retornou status, exibimos
        if resp.status:
            self._show_state(resp.status)

    def on_brightness_change(self, value):
        """Quando o usuário mexe no Scale de brilho (Lâmpada)"""
        brightness = int(float(value))
        self.send_cmd("SET_BRIGHTNESS", {"brightness": brightness})

    def on_set_temperature(self):
        """Define temperatura do ar-condicionado"""
        val = self.temp_entry.get().strip()
        if not val.isdigit():
            self.write_result("[ERRO] Temperatura inválida.")
            return
        temp = int(val)
        if temp < 16 or temp > 30:
            self.write_result("[ERRO] Temperatura deve ser entre 16 e 30.")
            return
        self.send_cmd("SET_TEMPERATURE", {"temperature": temp})

    def on_set_mode(self):
        """Define o modo (COOL, HEAT, FAN) do ar-condicionado"""
        mode = self.mode_var.get().upper()
        self.send_cmd("SET_MODE", {"mode": mode})

    def on_set_fan_speed(self):
        """Define a velocidade do ventilador (LOW, MEDIUM, HIGH, AUTO)"""
        speed = self.fan_var.get().upper()
        self.send_cmd("SET_FAN_SPEED", {"fan_speed": speed})

    # -------------------------------------
    # Exibir resultados no pop-up
    # -------------------------------------
    def write_result(self, text):
        self.txt_result.insert(tk.END, text + "\n")
        self.txt_result.see(tk.END)


# ===============================================
#          PAINEL DE ESTADO (REAL-TIME)
# ===============================================
class DeviceStatusPanel(tb.Frame):
    """
    Um painel que exibe em "tempo real" (ou em intervalos),
    as informações importantes dos dispositivos:
      - air_conditioner: power, temperature, mode, fan_speed
      - temperature_sensor: temperature
      - smart_lamp: power, brightness
      - etc.
    """
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.parent = parent
        self.device_labels = {}  # dict device_id -> label que mostra as info
        self.label_title = tb.Label(self, text="Status Atual dos Dispositivos", font="-size 12 -weight bold")
        self.label_title.pack(side=TOP, anchor="w", pady=5)

        # Frame interno para acomodar as "caixinhas" de cada device
        self.devices_frame = tb.Frame(self)
        self.devices_frame.pack(side=TOP, fill=X)

    def update_status(self, devices):
        """
        Recebe a lista de devices (ClientResponse.devices),
        e atualiza o painel. 
        """
        current_device_ids = [dev.device_id for dev in devices]

        # Remove cards antigos que não estão mais na lista
        for dev_id in list(self.device_labels.keys()):
            if dev_id not in current_device_ids:
                lbl = self.device_labels.pop(dev_id)
                lbl.destroy()

        # Atualiza/cria "cards" para cada device
        for dev in devices:
            dev_id = dev.device_id
            dev_type = dev.device_type
            # Tenta decodificar status como JSON
            info_str = ""
            try:
                state = json.loads(dev.status)
            except:
                state = {}

            if dev_type == "air_conditioner":
                power = state.get("power", "OFF")
                temp = state.get("temperature", "?")
                mode = state.get("mode", "?")
                fan_speed = state.get("fan_speed", "?")
                info_str = f"Air Conditioner [{dev_id}]\n  Power: {power}\n  Temp: {temp}\n  Mode: {mode}\n  Fan: {fan_speed}"

            elif dev_type == "temperature_sensor":
                sensor_temp = state.get("temperature", "?")
                unit = state.get("unit", "°C")
                info_str = f"Temperature Sensor [{dev_id}]\n  Temperature: {round(sensor_temp, 2)} {unit}"

            elif dev_type == "smart_lamp":
                power = state.get("power", "OFF")
                brightness = state.get("brightness", "?")
                info_str = f"Smart Lamp [{dev_id}]\n  Power: {power}\n  Brightness: {brightness}"

            elif dev_type == "brightness_sensor":
                sensor_bri = state.get("brightness", "?")
                unit = state.get("unit", "%")
                info_str = f"Brightness Sensor [{dev_id}]\n  Brightness: {round(sensor_bri, 2)} {unit}"

            elif dev_type == "power_sensor":
                sensor_pow = state.get("power", "?")
                unit = state.get("unit", "W")
                info_str = f"Power Sensor [{dev_id}]\n  Power: {round(sensor_pow, 2)} {unit}"

            else:
                # genérico
                info_str = f"{dev_type} [{dev_id}]\n  status: {dev.status}"

            if dev_id not in self.device_labels:
                lbl_card = tb.LabelFrame(self.devices_frame, text=dev_type, padding=5, bootstyle="info")
                lbl_card.pack(side=TOP, fill=X, pady=5, padx=5)

                lbl_info = tb.Label(lbl_card, text=info_str, justify=LEFT)
                lbl_info.pack(side=LEFT, anchor="w")

                self.device_labels[dev_id] = lbl_card
                self.device_labels[dev_id].lbl_info = lbl_info
            else:
                lbl_card = self.device_labels[dev_id]
                lbl_info = lbl_card.lbl_info
                lbl_info.config(text=info_str)


# ===============================================
#          JANELA PRINCIPAL (APP)
# ===============================================
class SmartHomeGUI(tb.Window):
    def __init__(self):
        super().__init__(themename="darkly")
        self.title("Smart Home - Interface Gráfica com Status em Tempo Real")
        self.geometry("1200x800")
        self.minsize(1000, 700)

        self.client = SmartHomeClient()

        # Logging e Filtros
        self.log_filters = {
            "[INFO]": True,
            "[ERRO]": True,
            "[ACTION]": True,
            "[RESPONSE]": True
        }

        # Layout principal
        self.create_top_frame()
        self.create_middle_frame()
        self.create_bottom_frame()

        # Painel de estado
        self.status_panel = DeviceStatusPanel(self.middle_frame_right)
        self.status_panel.pack(side=TOP, fill=BOTH, expand=True, padx=5, pady=5)

        # Inicia o loop de atualização periódica a cada 5s
        self.update_interval_ms = 5000
        self.start_periodic_update()

    # =============================================
    #   TOPO: Conexão
    # =============================================
    def create_top_frame(self):
        self.top_frame = tb.Frame(self)
        self.top_frame.pack(side=TOP, fill=X, padx=5, pady=5)

        frm_conn = tb.Labelframe(self.top_frame, text="Conexão com Gateway", bootstyle="primary")
        frm_conn.pack(side=LEFT, fill=BOTH, expand=True, padx=5, pady=5)

        lbl_ip = tb.Label(frm_conn, text="Gateway IP:")
        lbl_ip.grid(row=0, column=0, padx=5, pady=5)
        self.ip_entry = tb.Entry(frm_conn, width=15)
        self.ip_entry.insert(0, "127.0.0.1")
        self.ip_entry.grid(row=0, column=1, padx=5, pady=5)

        lbl_port = tb.Label(frm_conn, text="Porta:")
        lbl_port.grid(row=0, column=2, padx=5, pady=5)
        self.port_entry = tb.Entry(frm_conn, width=6)
        self.port_entry.insert(0, "6000")
        self.port_entry.grid(row=0, column=3, padx=5, pady=5)

        btn_connect = tb.Button(frm_conn, text="Conectar", command=self.on_connect, bootstyle=SUCCESS)
        btn_connect.grid(row=0, column=4, padx=10, pady=5)

        btn_disconnect = tb.Button(frm_conn, text="Desconectar", command=self.on_disconnect, bootstyle=DANGER)
        btn_disconnect.grid(row=0, column=5, padx=10, pady=5)

        self.conn_indicator = tb.Label(frm_conn, text="●", font="-size 14", foreground="red")
        self.conn_indicator.grid(row=0, column=6, padx=10)

        self.conn_status_label = tb.Label(frm_conn, text="[Desconectado]", foreground="red")
        self.conn_status_label.grid(row=0, column=7, padx=5)

    # =============================================
    #   MEIO (Dividido em 2: LEFT e RIGHT)
    # =============================================
    def create_middle_frame(self):
        self.middle_frame = tb.Frame(self)
        self.middle_frame.pack(side=TOP, fill=BOTH, expand=True, padx=5, pady=5)

        self.middle_frame_left = tb.Frame(self.middle_frame)
        self.middle_frame_left.pack(side=LEFT, fill=BOTH, expand=True)

        self.middle_frame_right = tb.Frame(self.middle_frame)
        self.middle_frame_right.pack(side=RIGHT, fill=BOTH, expand=True)

        # Frame principal de dispositivos (Treeview)
        frm_dev = tb.Labelframe(self.middle_frame_left, text="Dispositivos (LIST_DEVICES)", bootstyle="info")
        frm_dev.pack(side=TOP, fill=BOTH, expand=True, padx=5, pady=5)

        btn_list = tb.Button(frm_dev, text="Listar Dispositivos", command=self.on_list_devices, bootstyle=PRIMARY)
        btn_list.pack(side=TOP, anchor="nw", padx=5, pady=5)

        tree_container = tb.Frame(frm_dev)
        tree_container.pack(side=TOP, fill=BOTH, expand=True)

        columns = ("device_id", "device_type", "status", "ip_port")
        self.device_tree = tb.Treeview(tree_container, columns=columns, show="headings", bootstyle=INFO)
        self.device_tree.heading("device_id", text="Device ID")
        self.device_tree.heading("device_type", text="Tipo")
        self.device_tree.heading("status", text="Status")
        self.device_tree.heading("ip_port", text="IP:Porta")

        self.device_tree.column("device_id", anchor=tk.W, width=250)
        self.device_tree.column("device_type", anchor=tk.CENTER, width=120)
        self.device_tree.column("status", anchor=tk.W, width=300, stretch=True)
        self.device_tree.column("ip_port", anchor=tk.CENTER, width=120)

        vsb = tb.Scrollbar(tree_container, orient="vertical", command=self.device_tree.yview)
        hsb = tb.Scrollbar(tree_container, orient="horizontal", command=self.device_tree.xview)
        self.device_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=RIGHT, fill=Y)
        hsb.pack(side=BOTTOM, fill=X)
        self.device_tree.pack(side=LEFT, fill=BOTH, expand=True)

        self.device_tree.bind("<<TreeviewSelect>>", self.on_device_select)

        btn_cfg = tb.Button(frm_dev, text="Configurações Avançadas",
                            command=self.on_device_config, bootstyle=SECONDARY)
        btn_cfg.pack(side=BOTTOM, anchor="e", padx=5, pady=5)

    # =============================================
    #   BOTTOM: Logs
    # =============================================
    def create_bottom_frame(self):
        self.bottom_frame = tb.Frame(self)
        self.bottom_frame.pack(side=BOTTOM, fill=BOTH, expand=True, padx=5, pady=5)

        frm_log = tb.Labelframe(self.bottom_frame, text="Logs (Filtráveis)", bootstyle="secondary")
        frm_log.pack(side=TOP, fill=BOTH, expand=True)

        frm_filter = tb.Frame(frm_log)
        frm_filter.pack(side=TOP, fill=X)

        self.filter_buttons = {}
        for i, cat in enumerate(["[INFO]", "[ERRO]", "[ACTION]", "[RESPONSE]"]):
            var = tk.BooleanVar(value=True)
            btn = tb.Checkbutton(frm_filter, text=cat, variable=var,
                                 command=self.on_filter_change, bootstyle="tool")
            btn.grid(row=0, column=i, padx=5)
            self.filter_buttons[cat] = var

        self.log_text = tb.Text(frm_log, wrap="word")
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True, padx=5, pady=5)

        scroll = tb.Scrollbar(frm_log, command=self.log_text.yview)
        scroll.pack(side=LEFT, fill=Y)
        self.log_text.configure(yscrollcommand=scroll.set)

    # =============================================
    #   CALLBACKS DE DISPOSITIVOS
    # =============================================
    def on_device_select(self, event):
        selected_item = self.device_tree.focus()
        if not selected_item:
            return

    def on_device_config(self):
        selected_item = self.device_tree.focus()
        if not selected_item:
            self.write_log("Selecione um dispositivo na lista para configurar.", "[ERRO]")
            return

        values = self.device_tree.item(selected_item, "values")
        if len(values) < 4:
            self.write_log("Dispositivo inválido.", "[ERRO]")
            return

        dev_id, dev_type, dev_status, dev_ip_port = values
        if not dev_id:
            self.write_log("Dispositivo inválido (ID vazio).", "[ERRO]")
            return

        if not self.client.is_connected():
            self.write_log("Conecte-se ao Gateway primeiro.", "[ERRO]")
            return

        popup = DeviceConfigPopup(self, self.client, dev_id, dev_type)
        popup.grab_set()

    def on_list_devices(self):
        if not self.client.is_connected():
            self.write_log("Não está conectado ao Gateway.", "[ERRO]")
            return

        response, error = self.client.list_devices()
        if error:
            self.write_log(error, "[ERRO]")
            return

        if not response:
            self.write_log("Sem resposta do Gateway.", "[ERRO]")
            return

        if not response.success:
            self.write_log(f"Falha ao listar dispositivos: {response.message}", "[ERRO]")
            return

        self.write_log("Lista de dispositivos atualizada.", "[INFO]")

        for item in self.device_tree.get_children():
            self.device_tree.delete(item)

        for dev in response.devices:
            dev_id = dev.device_id
            dev_type = dev.device_type
            ip_port = f"{dev.ip}:{dev.port}"
            dev_status = dev.status
            self.device_tree.insert("", tk.END, values=(dev_id, dev_type, dev_status, ip_port))

        self.status_panel.update_status(response.devices)

    # =============================================
    #   AÇÕES DE CONEXÃO
    # =============================================
    def on_connect(self):
        ip = self.ip_entry.get().strip()
        port_str = self.port_entry.get().strip()
        if not port_str.isdigit():
            messagebox.showerror("Erro", "Porta inválida.")
            return
        port = int(port_str)
        self.client.gateway_ip = ip
        self.client.gateway_port = port

        success, msg = self.client.connect()
        if success:
            self.conn_indicator.config(foreground="green")
            self.conn_status_label.config(text="[Conectado]", foreground="green")
            self.write_log(msg, "[INFO]")
        else:
            self.write_log(msg, "[ERRO]")

    def on_disconnect(self):
        if self.client.is_connected():
            self.client.disconnect()
            self.conn_indicator.config(foreground="red")
            for item in self.device_tree.get_children():
                self.device_tree.delete(item)
            self.status_panel.update_status([])
            self.conn_status_label.config(text="[Desconectado]", foreground="red")
            self.write_log("Desconectado do Gateway.", "[INFO]")
        else:
            self.write_log("Já estava desconectado.", "[ERRO]")

    # =============================================
    #   LOGS
    # =============================================
    def write_log(self, text, category="[INFO]"):
        if category not in self.log_filters:
            return
        if not self.log_filters[category]:
            return
        self.log_text.insert(tk.END, f"{category} {text}\n")
        self.log_text.see(tk.END)

    def on_filter_change(self):
        for cat, var in self.filter_buttons.items():
            self.log_filters[cat] = var.get()

    # =============================================
    #   ATUALIZAÇÃO PERIÓDICA
    # =============================================
    def start_periodic_update(self):
        self.after(self.update_interval_ms, self.periodic_update)

    def periodic_update(self):
        if self.client.is_connected():
            response, error = self.client.list_devices()
            if response and response.success:
                self.status_panel.update_status(response.devices)

        self.after(self.update_interval_ms, self.periodic_update)


# ===============================================
#  PONTO DE ENTRADA
# ===============================================
if __name__ == "__main__":
    app = SmartHomeGUI()
    app.mainloop()
