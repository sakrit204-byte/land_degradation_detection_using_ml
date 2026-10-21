import time, pystac_client, planetary_computer as pc, odc.stac, numpy as np
cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
bbox=[85.90,26.95,85.95,27.00]
t=time.time()
items=list(cat.search(collections=["sentinel-2-l2a"],bbox=bbox,datetime="2023-03-01/2023-03-31",query={"eo:cloud_cover":{"lt":60}}).items())
print(len(items), [i.properties.get("s2:processing_baseline") for i in items][:5], time.time()-t)
ds=odc.stac.load(items,bands=["B04","B08","SCL"],bbox=bbox,resolution=10,crs="EPSG:32645",groupby="solar_day",chunks={})
ds=ds.compute(); print(ds, time.time()-t)
for c in ["sentinel-2-l2a","modis-13Q1-061","landsat-c2-l2","esa-worldcover","jrc-gsw","io-lulc-annual-v02","nasadem","hgb"]:
    try: print(c, cat.get_collection(c).extent.temporal.intervals)
    except Exception as e: print(c,"MISSING",e)
