#!/usr/bin/python
# -*- coding: utf-8 -*-


#    KmlMapServer is a web application to generate KML output from a mapfile
#    Copyright (C) 2009, Guillaume Sueur, Neogeo Technologies
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.




 
import random, sys, cgi, time, os, traceback, ConfigParser, psycopg2, zipfile
import mapscript
import math
import string
from mako.template import Template

# Windows doesn't always do the 'working directory' check correctly.
if sys.platform == 'win32':
    workingdir = os.path.abspath(os.path.join(os.getcwd(), os.path.dirname(sys.argv[0])))
    cfgfiles = (os.path.join(workingdir, "kmlmapserver.cfg"), os.path.join(workingdir,"..","kmlmapserver.cfg"))
else:
    #cfgfiles = ("/etc/kmlmapserver.cfg", os.path.join("..", "kmlmapserver.cfg"), "kmlmapserver.cfg")
    cfgfiles = "/etc/kmlmapserver.cfg"

class Error(Exception):
    """Base class for exceptions in this module."""
    pass

class InputError(Error):
    """Exception raised for errors in the input.

    Attributes:
        msg  -- explanation of the error
    """

    def __init__(self, msg):
        self.msg = msg
    def __str__(self):
        return repr(self.msg)

def random_filename(chars=string.hexdigits, length=16, prefix='',
          suffix='', verify=True, attempts=10):
    for attempt in range(attempts):
        filename = ''.join([random.choice(chars) for i in range(length)])
        filename = prefix + filename + suffix
        if not verify or not os.path.exists(filename):
            return filename
class Service (object):
    def __init__ (self, mapfile, params):
        self.layers   = None
        self.host = None
        self.mapfile = mapfile
        self.params = params
        self.bbox = None
        self.north = 90
        self.south = -90
        self.east = 180
        self.west = -180
        self.extra_fields = ''
              
    def set_bbox(self,bbox):
        self.bbox = bbox
        bbox = bbox.split(',')
        self.west = float(bbox[0])
        self.south = float(bbox[1])
        self.east = float(bbox[2])
        self.north = float(bbox[3])      
                    
    def _load (cls, *files):
        mapfile = None
        layers = {}
        params = {}
        config = None
        
        config = ConfigParser.ConfigParser()
        config.read(files)
        
        if config.has_section("main"):
            for key in config.options("main"):
                params[key] = config.get("main", key)
        service= cls(mapfile, params)
        if 'host' in params:
            service.host = params['host']
        return service 
    load = classmethod(_load)
    
    def get_layers_list(self, layer_name='all'):
        my_map = mapscript.mapObj(os.path.join(self.params['map_dir'],self.mapfile))
        try:
            map_label = my_map.getMetaData('wms_title')
        except:
            map_label = my_map.name
        layers_list = []
        for i in range(0,my_map.numlayers):
            layer = {}
            oLayer = my_map.getLayer(i)
            if layer_name == 'all' or layer_name == oLayer.name:
                # KML_ID is mandatory for the layer to be published
                try:
                    id_is_declared = oLayer.getMetaData('KML_ID')
                except:
                    continue 
                try:
                    kml_layer_name = oLayer.getMetaData("wms_title")
                except:
                    kml_layer_name = oLayer.name
                    
                layer['label'] = kml_layer_name
                layer['name'] = oLayer.name
                layers_list.append(layer)
        logo_url = "https://download.recette.data.grandlyon.com/files/grandlyon/logos/%s.jpg" % (self.mapfile.replace('.map',''))
        template_file = os.path.join(os.path.dirname(os.path.realpath( __file__ )),'Templates/list.xml')
        my_template = Template(filename=template_file, default_filters=['decode.utf8'], input_encoding='utf-8')
        
        strKML =  my_template.render_unicode(
                host = self.host,
                mapfile = self.mapfile,
                map_label = map_label,
                layers_list = layers_list,
                logo_url = logo_url
        ).encode('utf-8', 'replace')

        return self.kmz_output(strKML)

    def get_postgis_data(self, my_layer,max_features):
        str_bbox = "ST_GeomFromText('POLYGON((%f %f,%f %f,%f %f,%f %f,%f %f))',4326)" % (self.west, self.south, self.west, self.north, self.east, self.north, self.east, self.south, self.west, self.south)
        simplify_factor =  math.fabs(self.east - self.west) / 1000
        str_data = my_layer.data
        col_geom = str_data.split(' ')[0]
        sql_pieces = string.upper(str_data).split(' FROM ')
        table_name = string.lower(sql_pieces[-1].split(' ')[0].replace(')',''))
        
        try:
            col_id = my_layer.getMetaData('KML_ID')
        except:
            return ""
        try:
            col_name = my_layer.getMetaData('KML_NAME')
        except:
            col_name = col_id
        try:
            col_name = my_layer.getClass(0).getTextString().split('[')[1].split(']')[0]
        except:
            pass
        str_where = " WHERE ST_Transform(%s,4326) && %s " % (col_geom, str_bbox)
        if my_layer.type == mapscript.MS_LAYER_POLYGON:
            try:
                if my_layer.getMetaData('KML_CLIP') == 'TRUE':
                    str_where = " WHERE ST_Transform(%s,4326) && %s AND NOT ST_IsEmpty(ST_Buffer(ST_Intersection(ST_Transform(%s,4326),%s),0.0))" % (col_geom, str_bbox, col_geom, str_bbox)
            except:
                pass
        filter_field = ''
        if my_layer.getFilterString():
            if str_where == '':
                str_where = " WHERE %s" % (my_layer.getFilterString().replace('"',''))
            else:
                str_where += " AND %s" % (my_layer.getFilterString().replace('"',''))
            filter_field = my_layer.getFilterString().split('"')[1]

        if filter_field != '':
            col_filter = filter_field
            filter_field = ',' + filter_field
        else:
            col_filter = col_id 
        
        conn = psycopg2.connect(my_layer.connection);
        cur = conn.cursor()
        
        str_geom = "ST_asKML(ST_Transform(%s,4326))" % (col_geom)
        try:
            simplify = my_layer.getMetaData('KML_SIMPLIFY')
        except:
            simplify = "TRUE"
        
        if my_layer.type == mapscript.MS_LAYER_POLYGON and simplify == 'TRUE':
            str_geom = "ST_asKML(ST_Simplify(ST_Transform(%s,4326),%f))" % (col_geom, simplify_factor)
            try:
                if my_layer.getMetaData('KML_CLIP') == 'TRUE' :
                    str_geom = "ST_asKML(ST_Buffer(ST_Intersection(ST_Simplify(ST_Transform(%s,4326),%f),%s),0.0))"% (col_geom,simplify_factor,str_bbox)
            except:
                pass
        elif my_layer.type == mapscript.MS_LAYER_POLYGON :
            str_geom = "ST_asKML(ST_Transform(%s,4326))" % (col_geom)
            try:
                if my_layer.getMetaData('KML_CLIP') == 'TRUE' :
                    str_geom = "ST_asKML(ST_Buffer(ST_Intersection(ST_Transform(%s,4326),%s),0.0))"% (col_geom,str_bbox)
            except:
                pass
        try:    
            kml_extra_fields = my_layer.getMetaData('KML_EXTRA_FIELDS')
            if kml_extra_fields != '':
                self.extra_fields = kml_extra_fields
                sql_extra_fields = "," + kml_extra_fields + filter_field
            else:
                self.extra_fields = ""
                sql_extra_fields = "" + filter_field
        except:
            self.extra_fields = ""
            sql_extra_fields = "" + filter_field
        strSQL = "SELECT %s,%s,%s, %s %s from %s %s;" % (col_id,col_name,col_filter,str_geom,sql_extra_fields,table_name,str_where)
        h = open('/tmp/logsql.txt','w')
        h.write(strSQL+ '\n')
        h.close()
        
        # requete pour le calcul du nombre d'objets
        strSQLCount = "SELECT count(%s) from %s %s" % (col_id,table_name,str_where) 
        cur.execute(strSQLCount)
        r = cur.fetchone()
        nb_features = r[0]
        
        if nb_features > max_features:
            # send a WMS link instead of KML placemarks if amount too huge
            try:
                kml_layer_name = my_layer.getMetaData("wms_title")
            except:
                kml_layer_name = my_layer.name
            return self.dump_as_WMS(my_layer.name, kml_layer_name)                 
        try:
            cur.execute(strSQL)
        except:
            h = open(os.path.join(self.params['temp_dir'],'logsql.txt'),'w')
            h.write(strSQL+ '\n')
            h.write("%s" % (nb_features))
            h.close()
            return "Error in SQL string %s" % strSQL
        return cur.fetchall()
        
    def dispatch_layer(self, layer_names, max_features=None):
        
        my_map = mapscript.mapObj(os.path.join(self.params['map_dir'],self.mapfile))
        placemarks = []
        styles = []
        for layer_name in layer_names.split(','):
            
            my_layer = my_map.getLayerByName(string.strip(layer_name))
            if not my_layer:
                return ""
                
            styles.extend(self.generate_styles(my_layer))
            try:
                kml_layer_name = my_layer.getMetaData("wms_title")
            except:
                kml_layer_name = my_layer.name
            if not max_features:
                try:
                    max_features = int(my_layer.getMetaData('KML_MAX_FEATURES'))
                except:
                    max_features = int(self.params['max_features'])
            if my_layer.connectiontype == mapscript.MS_POSTGIS:
                res = self.get_postgis_data(my_layer,max_features)
                # check if result is string (KML containing WMS link) or not
                if isinstance(res, str):
                    return res
                
                for r in res:
                    class_added = False
                    style_id = 0
                    #if my_layer.classitem:
                    for i in range(0,my_layer.numclasses):
                        my_class = my_layer.getClass(i)
                        if my_class.getExpressionString():
                            reg_expr = str(my_class.getExpressionString()).split(']')[1].replace(')','').replace(' =','==')
                            #if len(reg_expr) > 1:
                            #if reg_expr[1] == str(r[len(r)-1]):
                            try:
				if eval(str(r[len(r)-1])+reg_expr):
                                    style_id = i
                                    class_added = True
                                    break
			    except:
 				continue
                            #else:
                            #    style_id = i
                            #    class_added = True
                            #    break
                        else:
                            style_id = i
                            class_added = True
                            break
                            
                    
                    if not my_layer.classitem or class_added:
                        placemark = {
                            'id' :  str(r[0]),
                            'name' : str(r[1]),
                            'styleUrl': "#Style_%s_%s" % (style_id, my_layer.name)
                        }
                        
                        #--- add optional fields required by 'KML_EXTRA_FIELDS' in map file
                        cpt = 4
                        if self.extra_fields != '':
                            description = "<table>"
                            for t in self.extra_fields.split(','):
                                field_name = t.replace(' ','')
                                placemark[field_name] = r[cpt]
                                description += "<tr><td>%s :</td><td> %s</td></tr>" % (field_name, r[cpt])
                                cpt += 1
                            description += "</table>"
                            placemark['description'] = description 
                        # ------------------------------------
                            
                        
                        
                        elif my_class.name:    
                            placemark['description'] = my_class.name
                        else:
                            placemark['description'] = my_layer.name
                        
                        if r[3]:
                            placemark['geom'] = r[3]
                            placemarks.append(placemark)
                        
        template_file = os.path.join(os.path.dirname( os.path.realpath( __file__ ) ),'Templates/layer.xml')
        my_template = Template(filename=template_file, default_filters=['decode.utf8'], input_encoding='utf-8')
       
        
        strKML =  my_template.render_unicode(
                layer_label = kml_layer_name,
                styles = styles,
                placemarks = placemarks
        ).encode('utf-8', 'replace')
        
        return self.kmz_output(strKML)
       
    def generate_styles(self,the_layer):
        try:
            balloon_style = the_layer.getMetaData("KML_DESCRIPTION")
        except:
            balloon_style = "<h1 style='color:#A85F2A;font-size:14px;font-weight:bold;margin:0px;'>$[name]</h1><div>$[description]</div>"
        
        styles = []
        for i in range(0,the_layer.numclasses):
            oClass = the_layer.getClass(i)
            if the_layer.type == mapscript.MS_LAYER_POINT:
                icon_url = "%s?request=icon&map=%s&typename=%s&classnum=%d" % (self.host,self.mapfile,the_layer.name,i)
                icon_size = oClass.getStyle(0).size 
                icon_scale = icon_size / 32
                if icon_scale < 0.2:
                    icon_scale = 0.2
                style = {
                     'style_id' : "%s_%s" % (i,the_layer.name),
                     'balloon_style' : balloon_style,
                     'icon_url' : icon_url,
                     'icon_scale' : icon_scale,
                     'style_type' : 'point'
                }
            else:
                line_width = -1
                color = line_color = ''
                col = None
                ocol = None
                
                for j in range(0,oClass.numstyles):
                    if oClass.getStyle(j).color.blue > -1:
                        col = oClass.getStyle(j).color
                    if oClass.getStyle(j).outlinecolor.blue > -1:
                        ocol = oClass.getStyle(j).outlinecolor
                        if oClass.getStyle(j).size > -1:
                            line_width = oClass.getStyle(j).size
                        elif oClass.getStyle(j).width > -1:
                            line_width = oClass.getStyle(j).width
                        
                if line_width < 2:
                    line_width = 2
                if ocol:
                    line_color = 'ff%02x%02x%02x' % (ocol.blue,ocol.green,ocol.red)
                    #style_type = 'line'
                if col :
                    if col.blue != -1:
                        color = 'aa%02x%02x%02x' % (col.blue,col.green,col.red)
                    else:
                        color = '00ffffff'
                    #style_type = 'polygon'
                if the_layer.type == mapscript.MS_LAYER_LINE and ocol is None:
                    ocol = oClass.getStyle(j).color
                    line_color = 'ff%02x%02x%02x' % (ocol.blue,ocol.green,ocol.red)
                    style_type = 'line'
                else:
                    if col:
                        style_type = 'polygon'
                    else:
                        style_type = 'polygon'
                        color = '00ffffff'

                style = {
                       'style_id' : "%s_%s" % (i,the_layer.name),
                       'line_width' : line_width,
                       'line_color' : line_color,
                       'color' : color,
                       'balloon_style' : balloon_style,
                       'style_type' : style_type
                }
            styles.append(style)
        
        return styles  
    
    def get_icon(self,layer_name,index): 
        import datetime
        my_map = mapscript.mapObj(os.path.join(self.params['map_dir'],self.mapfile))
        my_layer = my_map.getLayerByName(layer_name)
        oClass = my_layer.getClass(int(index))
        oClass.getStyle(0).size = 32
        icon_size = oClass.getStyle(0).size
        img = oClass.createLegendIcon(my_map,my_layer,int(icon_size),int(icon_size))
        key = str(datetime.datetime.now()).replace(' ','_')
        imgFile = os.path.join(self.params['temp_dir'],'legend_%s.png' % (key))
        img.save(imgFile)
        h = open(imgFile , 'r') 
        os.unlink(imgFile)
        return h.read()

    def dump_as_WMS(self,layer_name, kml_layer_name):
        
        base_size = 1400
        geo_width = self.east - self.west
        geo_height = self.north - self.south
        if geo_width > geo_height:
            screen_width=base_size
            screen_height=int(screen_width/(geo_width/geo_height)) + 200
        else:
            screen_height = base_size
            screen_width = int(screen_height/(geo_height/geo_width))
        
        str_wms = self.params['wms_url'] + "REQUEST=GetMap&SERVICE=WMS&VERSION=1.1.1&SRS=EPSG:4326&map=%s&layers=%s&format=image/png&width=%s&height=%s&bbox=%s,%s,%s,%s" % (os.path.join(self.params['map_dir'],self.mapfile), layer_name, screen_width, screen_height,self.west,self.south,self.east,self.north)
        template_file = os.path.join(os.path.dirname( os.path.realpath( __file__ ) ),'Templates/wms.xml')
        
        my_template = Template(filename=template_file, default_filters=['decode.utf8'], input_encoding='utf-8')
       
        strKML =  my_template.render_unicode(
                wms_url = str_wms,
                layer_label = kml_layer_name,
                north = self.north,
                south = self.south,
                east = self.east,
                west = self.west
        ).encode('utf-8', 'replace')

       
        return self.kmz_output(strKML)
        
        
    
    
    def kmz_output(self,resKML):    
        import datetime
        key = random_filename() 
        kmlName = os.path.join(self.params['temp_dir'],key + '.kml')
        kmzName = kmlName.replace('.kml','.kmz')
        h = open(kmlName,'w')
        
        h.write(resKML)
        h.close()
        #h = open(os.path.join(self.params['temp_dir'],'logkml.txt'),'w')
        #h.write(resKML)
        #h.close()
        z = zipfile.ZipFile(str(kmzName),'w', zipfile.ZIP_DEFLATED)
        z.write(kmlName, arcname=key+'.kml')
        z.close()
        handle = open(kmzName,'rb')
        #handle = open(kmlName,'r')
        os.unlink(kmzName)
        os.unlink(kmlName)
        return handle.read()

def cgiHandler (service):
    
    try:
        form = cgi.FieldStorage()
        if form.has_key('map'):
            service.mapfile = form.getvalue('map') 
        else:
            service.mapfile = service.params['map_name'] 
        if service.host == '':
            path_info =""
    
            if "PATH_INFO" in os.environ: 
                path_info = os.environ["PATH_INFO"]
            
            if "HTTP_X_FORWARDED_HOST" in os.environ:
                service.host      = "http://" + os.environ["HTTP_X_FORWARDED_HOST"]
            elif "HTTP_HOST" in os.environ:
                service.host      = "http://" + os.environ["HTTP_HOST"]
    
            service.host += os.environ["SCRIPT_NAME"]

        if form.has_key('request'):
            request = form.getvalue('request')
            
            if form.has_key('bbox'):
                service.set_bbox(form.getvalue('bbox'))
            elif form.has_key('BBOX'):
                service.set_bbox(form.getvalue('BBOX'))
            else:
                service.set_bbox(service.params['bbox'])
            
            if request == 'list':
                if form.has_key('typename'):
                    layer_name = form.getvalue('typename')
                else:
                    layer_name = 'all'    
                response = service.get_layers_list(layer_name)
                format = 'application/vnd.google-earth.kmz'
            elif request == 'layer' and form.has_key('typename'):
                if form.has_key('maxpoints'):
                    max_features = int(form.getvalue('maxpoints'))
                else:
                    max_features = None
                response = service.dispatch_layer(form.getvalue('typename'),max_features)
                #format = 'text/plain'
                format = 'application/vnd.google-earth.kmz'
            elif request == 'icon':
                response = service.get_icon(form.getvalue('typename'),form.getvalue('classnum'))
                format = 'image/png'
            else:
                raise InputError('Uncorrect request submitted.')
        
        else:
            raise InputError('No request submitted')
        
        print "Content-type: %s\n" % format
        if sys.platform == "win32":
            binaryPrint(response)
        else:    
            print response
        
    except InputError:
        print "Incomplete Form"
        raise
    
    
def modPythonHandler (apacheReq, service):
    from mod_python import apache, util
    if service.host == '':
        if apacheReq.headers_in.has_key("X-Forwarded-Host"):
            host = "http://" + apacheReq.headers_in["X-Forwarded-Host"]
        else:
            host = "http://" + apacheReq.headers_in["Host"]
        host += apacheReq.uri[:-len(apacheReq.path_info)]
        service.host = host + '/'
    params = util.FieldStorage(apacheReq)
    if params.has_key('map'):
        service.mapfile = params['map'] 
    else:
        service.mapfile = service.params['map_name'] 

    if params.has_key("request"):
        request = params['request']
        if params.has_key('bbox'):
            service.set_bbox(params['bbox'])
        elif params.has_key('BBOX'):
            service.set_bbox(params['BBOX'])
        else:
            service.set_bbox(service.params['bbox'])
        
        if request == 'list':
            if params.has_key('typename'):
                layer_name = params['typename']
            else:
                layer_name = 'all'    
            response = service.get_layers_list(layer_name)
            format = 'application/vnd.google-earth.kmz'
        elif request == 'layer' and params.has_key('typename'):
            if params.has_key('maxpoints'):
                max_features = int(params['maxpoints'])
            else:
                max_features = None
            response = service.dispatch_layer(params['typename'],max_features)
            format = 'application/vnd.google-earth.kmz'
        elif request == 'icon':
            response = service.get_icon(params['typename'],params['classnum'])
            format = 'image/png'
        else:
            raise InputError('Uncorrect request submitted.')
    else:
        raise InputError('No request submitted')
    
    apacheReq.content_type = format
    apacheReq.status = apache.HTTP_OK
    apacheReq.send_http_header()
    apacheReq.write(response)
    
        
    return apache.OK

theService = {}
lastRead = {}

def WSGIHandler(environ, start_response, service):
    import cgi
    form = cgi.FieldStorage(fp=environ['wsgi.input'], 
                        environ=environ)
    
    try:
        
        if form.has_key('map'):
            service.mapfile = form.getvalue('map') 
        else:
            service.mapfile = service.params['map_name'] 
        if service.host == '':
            path_info =""
    
            if "PATH_INFO" in os.environ: 
                path_info = os.environ["PATH_INFO"]
            
            if "HTTP_X_FORWARDED_HOST" in os.environ:
                service.host      = "http://" + os.environ["HTTP_X_FORWARDED_HOST"]
            elif "HTTP_HOST" in os.environ:
                service.host      = "http://" + os.environ["HTTP_HOST"]
    
            service.host += os.environ["SCRIPT_NAME"]

        if form.has_key('request'):
            request = form.getvalue('request')
            
            if form.has_key('bbox'):
                service.set_bbox(form.getvalue('bbox'))
            elif form.has_key('BBOX'):
                service.set_bbox(form.getvalue('BBOX'))
            else:
                service.set_bbox(service.params['bbox'])
            
            if request == 'list':
                if form.has_key('typename'):
                    layer_name = form.getvalue('typename')
                    filename = '%s.kmz' % layer_name
                else:
                    layer_name = 'all'   
                    filename = 'GrandLyon.kmz'
                response = service.get_layers_list(layer_name)
                format = 'application/vnd.google-earth.kmz'
            elif request == 'layer' and form.has_key('typename'):
                if form.has_key('maxpoints'):
                    max_features = int(form.getvalue('maxpoints'))
                else:
                    max_features = None
                filename = '%s.kmz' % form.getvalue('typename')
                response = service.dispatch_layer(form.getvalue('typename'),max_features)
                #format = 'text/plain'
                format = 'application/vnd.google-earth.kmz'
                #format = 'application/vnd.google-earth.kml+xml'
            elif request == 'icon':
                response = service.get_icon(form.getvalue('typename'),form.getvalue('classnum'))
                format = 'image/png'
                filename = 'icon.png'
            else:
                raise InputError('Uncorrect request submitted.')
        
        else:
            raise InputError('No request submitted')
        status = '200 OK'
        response_headers = [("Content-type", "%s" % format),
            ('Content-Length', str(len(response))),
            ('Content-disposition', 'attachment; filename=%s' % filename)    
        ]
        start_response(status, response_headers)
        return [response]
        
    except InputError:
        print "Incomplete Form"
        raise 

#WSGI Handler
def application(environ, start_response):
    global theService
    cfgs    = cfgfiles
    if not theService:
        theService = Service.load(cfgs)
    return WSGIHandler(environ, start_response, theService)
    
    
def handler (apacheReq):
    global theService, lastRead
    options = apacheReq.get_options()
    cfgs    = cfgfiles
    fileChanged = False
    if options.has_key("KmlMapServerConfig"):
        configFile = options["KmlMapServerConfig"]
        lastRead[configFile] = time.time()
        
        cfgs = cfgs + (configFile,)
        try:
            cfgTime = os.stat(configFile)[8]
            fileChanged = lastRead[configFile] < cfgTime
        except:
            pass
    else:
        configFile = 'default'
        
    if not theService.has_key(configFile) or fileChanged:
        theService[configFile] = Service.load(*cfgs)
        
    return modPythonHandler(apacheReq, theService[configFile])   

if __name__ == '__main__':
    svc = Service.load(*cfgfiles)
    cgiHandler(svc)
