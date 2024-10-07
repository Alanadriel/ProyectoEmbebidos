

import time
import machine
import micropython
import network
from machine import Pin,PWM
from umqtt.simple import MQTTClient
import dht
import tm1637
from tm1637 import TM1637
from config import ssid, wifipassword, mqtt_server,client_id,user, password,port


#Indicamos ID(unico) y topicos

topic_BH = 'AguiLuciCami/feeds/EncenderHorno'  #topico boton encendido/apagado
topic_TD = 'AguiLuciCami/feeds/Temperatura'#topico temperatura deseada
topic_TIMED = 'AguiLuciCami/feeds/Timer' #topico tiempo deseado
topic_Alarma = 'AguiLuciCami/feeds/Alarma' #topico de la alarma que le avisa al usurio cuando ya paso el tiempo

#Definicion de variables
V_DESTEMP= -1
v_TIEMPO= -1
SobreCalentamiento= 0
HORNO_ACTIVO=False
LEDESTADOH = Pin(5,Pin.OUT) 
Sensortemp= dht.DHT22(Pin(32))
LEDTEMPOBJ = Pin(4,Pin.OUT)
LEDEALARMA = Pin(14,Pin.OUT)
display= TM1637(Pin(33),Pin(25))
SIRENA = PWM(Pin(12), freq=1200, duty_u16=32768)
SIRENA.duty(0)
SONANDO=False
#Definimos modo Station (conectarse a Access Point remoto)
sta_if = network.WLAN(network.STA_IF)
sta_if.active(True)
#Conectamos al wifi
sta_if.connect(ssid, wifipassword)
print("Conectando")
while not sta_if.isconnected():
  print(".", end="")
  time.sleep(0.1)
print("Conectado a Wifi!")
#Vemos cuales son las IP
print(sta_if.ifconfig())
#Antes de conectarnos al broker, vamos a definir una funcion
#que sera llamada cada vez que se produzca un publish sobre
#un topico donde estamos suscriptos
def callback_horno(topic, msg):
    global HORNO_ACTIVO,LEDESTADOH, V_DESTEMP, v_TIEMPO
    #Cuando se ejecuta esta funcion quere decir que
    #hubo un mensaje nuevo en algun topico, verificamos esto
    #Dado que lo que llega viene en UTF-8, lo decodificamos
    #para que sea una cadena de texto regular
    dato = msg.decode('utf-8')
    topicrec = topic.decode('utf-8')
    print("Cambio en: "+topicrec+":"+dato)
    #Nos fijamos si es el topico esperado y el valor del dato
    if topicrec == topic_BH and "OFF" in dato:
        HORNO_ACTIVO=False
        LEDESTADOH.value(HORNO_ACTIVO)
    elif topicrec == topic_BH and "ON" in dato:
        HORNO_ACTIVO=True
        LEDESTADOH.value(HORNO_ACTIVO)
    if topicrec == topic_TD: 
         V_DESTEMP= int(dato)
    if topicrec == topic_TIMED:
        v_TIEMPO= int(dato)
    if topicrec == topic_Alarma and "OFF" in dato:
        SONANDO=False
        LEDEALARMA.value(SONANDO)
        SIRENA.duty(0)


#Intentamos conectarnos al broker MQTT
try:
    conexionMQTT = MQTTClient(client_id, mqtt_server,user=user,password=password,port=int(port))
    conexionMQTT.set_callback(callback_horno)
    conexionMQTT.connect()
    conexionMQTT.subscribe(topic_BH)
    conexionMQTT.subscribe(topic_TD)
    conexionMQTT.subscribe(topic_TIMED)
    conexionMQTT.subscribe(topic_Alarma)
    print("Conectado con Broker MQTT")
except OSError as e:
    #Si fallo la conexion, reiniciamos todo
    print("Fallo la conexion al Broker, reiniciando...")
    time.sleep(5)
    machine.reset()

# Esta bandera sirve para verificar si en el estado de sobrecaliente el horno va bajando la temperatura o no
Band=False
#Funcion para que cuando el horno este en estado de sobrecalietamiento vaya bajando su temperatura
def FSCalent (tempH,tempD):
    global HORNO_ACTIVO,LEDESTADOH,topic_BH,Band,LEDTEMPOBJ
    HORNO_ACTIVO=True
    LEDESTADOH.value(HORNO_ACTIVO)
    time.sleep(1)
    conexionMQTT.publish(topic_BH,"ON")
    tempH = Sensortemp.temperature()
    while Band:
        if tempH<=tempD:
            HORNO_ACTIVO=True
            LEDESTADOH.value(HORNO_ACTIVO)
            time.sleep(1)
            conexionMQTT.publish(topic_BH,"ON")
            Band=False
        else:
            HORNO_ACTIVO=False
            LEDESTADOH.value(HORNO_ACTIVO)
            time.sleep(1)
            conexionMQTT.publish(topic_BH,"OFF")
            Band=True
            LEDTEMPOBJ.value(0)
#Esta variable sirve para que saber cuando la alarma suena y esta pueda salir del ciclo
variable=True
#Logica del horno
while True:
    conexionMQTT.check_msg()
    time.sleep_ms(500)
    #Leemos nuevas valores
    Sensortemp.measure()
    hornotemp = Sensortemp.temperature()
    try:
        if HORNO_ACTIVO:
            SobreCalentamiento=V_DESTEMP+10
            if hornotemp>=V_DESTEMP and hornotemp<(V_DESTEMP+1):
                LEDTEMPOBJ.value(1)
                #CONVIERTO LOS MINUTOS EN SEGUNDOS para el display
                contador=v_TIEMPO*60
                if v_TIEMPO>0:
                    BandVerificacion=0 #sirve para verificar que la temperatura del horno no supere el rango permitido
                    while variable:
                        if contador==0 and BandVerificacion==0:
                            SONANDO=True
                            LEDEALARMA.value(SONANDO)
                            SIRENA.duty(512)
                            conexionMQTT.publish(topic_Alarma,"ON")
                            variable=False
                        else:
                            if BandVerificacion==0:
                                Sensortemp.measure()
                                nuevatemp = Sensortemp.temperature()  #Actualizo la temperatura
                                if nuevatemp>=SobreCalentamiento:
                                    HORNO_ACTIVO=False
                                    LEDESTADOH.value(HORNO_ACTIVO)
                                    conexionMQTT.publish(topic_BH,"OFF")
                                    LEDTEMPOBJ.value(0)
                                    BandVerificacion=1
                                    break
                                elif nuevatemp>=V_DESTEMP and nuevatemp<SobreCalentamiento:
                                    time.sleep_ms(1)
                                    display.number(contador)
                                    contador=contador-1
                                    display.number(contador)
                                    BandVerificacion=0    
                     
            if hornotemp>=SobreCalentamiento and v_TIEMPO!=0:
                HORNO_ACTIVO=False
                LEDESTADOH.value(HORNO_ACTIVO)
                conexionMQTT.publish(topic_BH,"OFF")
                LEDTEMPOBJ.value(0)
                FSCalent(hornotemp,V_DESTEMP)
    except OSError as e:
        print("Error ",e)
        time.sleep(5)
        machine.reset()