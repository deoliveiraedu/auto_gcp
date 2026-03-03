import re
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS, IFD

def parse_dji_xmp(xmp_str):
    """Extrai os metadados específicos da DJI do bloco XMP."""
    data = {}
    
    # Padrão: drone-dji:NomeDaTag="Valor" ou similar em XML
    # Algumas versões da DJI usam drone-dji:GimbalYawDegree ou dji-sdk:GimbalYawDegree
    pattern = r'([a-zA-Z-]+):([a-zA-Z]+)="([^"]+)"'
    matches = re.findall(pattern, xmp_str)
    
    for prefix, key, value in matches:
        if 'dji' in prefix.lower():
            try:
                data[key] = float(value)
            except ValueError:
                data[key] = value
            
    return data

def get_image_metadata(img_path):
    """
    Retorna um dicionário com:
    - width, height
    - lat, lon, alt (WGS84 via EXIF)
    - gimbal_yaw, gimbal_pitch, gimbal_roll (via XMP)
    - focal_length (mm), focal_length_35mm (mm)
    """
    meta = {}
    
    with Image.open(img_path) as img:
        meta['width'] = img.width
        meta['height'] = img.height
        
        exif = img.getexif()
        
        # Extrair Focal Length do EXIF básico
        ifd = exif.get_ifd(IFD.Exif)
        if ifd:
            for k, v in ifd.items():
                tag = TAGS.get(k, k)
                if tag == 'FocalLengthIn35mmFilm':
                    meta['focal_length_35mm'] = float(v)
                elif tag == 'FocalLength':
                    try: meta['focal_length'] = float(v)
                    except: pass
        
        # Extrair GPS do EXIF
        gps_info = exif.get_ifd(IFD.GPSInfo)
        if gps_info:
            gps_data = {}
            for t in gps_info:
                sub_decoded = GPSTAGS.get(t, t)
                gps_data[sub_decoded] = gps_info[t]
                
            def convert_to_degrees(value):
                try:
                    d = float(value[0])
                    m = float(value[1])
                    s = float(value[2])
                    return d + (m / 60.0) + (s / 3600.0)
                except: return 0.0

            lat = gps_data.get("GPSLatitude")
            lat_ref = gps_data.get("GPSLatitudeRef")
            lon = gps_data.get("GPSLongitude")
            lon_ref = gps_data.get("GPSLongitudeRef")
            alt = gps_data.get("GPSAltitude")
            
            if lat and lat_ref and lon and lon_ref:
                dec_lat = convert_to_degrees(lat)
                if str(lat_ref).upper() != "N": dec_lat = -dec_lat
                meta['lat'] = dec_lat
                
                dec_lon = convert_to_degrees(lon)
                if str(lon_ref).upper() != "E": dec_lon = -dec_lon
                meta['lon'] = dec_lon
                
            if alt is not None:
                try: meta['alt'] = float(alt)
                except: pass

        # Extrair XMP para Gimbal / Altura Absoluta e Relativa (DJI)
        xmp_data = {}
        # Forma moderna de pegar XMP no Pillow
        if hasattr(img, 'applist'):
            for app in img.applist:
                if b'http://ns.adobe.com/xap/1.0/\x00' in app[1]:
                    xmp_str = app[1].decode('utf-8', errors='ignore')
                    xmp_data = parse_dji_xmp(xmp_str)
                    break
        elif 'xmp' in img.info:
            # Caso o Pillow já tenha extraído para img.info
            xmp_str = img.info['xmp']
            if isinstance(xmp_str, bytes):
                xmp_str = xmp_str.decode('utf-8', errors='ignore')
            xmp_data = parse_dji_xmp(xmp_str)
        
        # Defaults para DJI Mini 2 e similares
        meta['gimbal_yaw'] = xmp_data.get('GimbalYawDegree', 0.0)
        meta['gimbal_pitch'] = xmp_data.get('GimbalPitchDegree', -90.0)
        meta['gimbal_roll'] = xmp_data.get('GimbalRollDegree', 0.0)
        
        if 'AbsoluteAltitude' in xmp_data and 'alt' not in meta:
            meta['alt'] = xmp_data['AbsoluteAltitude']
        if 'RelativeAltitude' in xmp_data:
            meta['rel_alt'] = xmp_data['RelativeAltitude']

    return meta
