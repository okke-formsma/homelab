todo:
* set up PIDs https://gathering.tweakers.net/forum/list_message/83609702#83609702
* make multiple rooms & kleppen work standalone and/or with HA

### DEVICES

huis
192.168.1.244

garage
192.168.1.205

ARP tabel: https://192.168.1.1/ARPTable

This device is using only humidity sensor now, with a hardcoded pattern.

workon esphome
pip install --update esphome
esphome run open-air-mini-huis.yaml --device 192.168.1.244
esphome logs open-air-mini-huis.yaml --device 192.168.1.244

esphome run open-air-mini-garage.yaml --device 192.168.1.205
