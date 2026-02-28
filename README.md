First real github made public (Very much a work in progress). Kitchen inventory system with an info panel made for Raspberry Pi with screens to be put in a kitchen. 

Kitchen side of the application lets you select a save location, scan the barcode, then it keeps track of the qty, location, # of uses, and you scan it out once its all used.
Anything thast hits 0 gets added to grocery list, items you select with a threshold you set get added to a low stock list once they hit the target number or less. 

Info Panel side lets you see the weather: current forcast, an hourly 12 hr forcast, tomorrows forcast, weather ALERTS, radar gif. Homelab Ping moniter, Alerts/Events page, RF signals page that doesnt really work at the moment. 

Fresh install

  git clone https://github.com/Alpha8056/StockPi-InfoPanel.git
  chmod +x setup.sh && sudo ./setup.sh

Update to the newest github push
  cd ~/StockPi-InfoPanel && git pull
