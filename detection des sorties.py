import pyaudio

p = pyaudio.PyAudio()

# Récupérer les infos de l’API hôte (généralement index 0)
api_info = p.get_host_api_info_by_index(0)
numdevices = api_info.get('deviceCount')

print("Périphériques de sortie disponibles :")
for i in range(numdevices):
    dev = p.get_device_info_by_host_api_device_index(0, i)
    if dev.get('maxOutputChannels') > 0:
        print(f"  ID {i} : {dev.get('name')} ({dev.get('maxOutputChannels')} canaux)")  #

p.terminate()
