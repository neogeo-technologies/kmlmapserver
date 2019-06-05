===========
 KmlMapServer
===========

-------------------------
Serve mapfile content as KML stream
-------------------------

:Author: Guillaume Sueur, Neogeo Technologies
:Date:   2009-03-12
:Copyright: (c) 2009 Neogeo Technologies
            Distributed under the GPLv3 license.
:Version: 0.2


DESCRIPTION
===========
KmlMapServer is designed to generate a KML output matching 
filters and representations set in a MapServer mapfile. At the moment, it only works with PostGIS
layers.

INSTALLING KMLMAPSERVER
====================

Generally, installing KmlMapServer is as simple as downloading a source
distribution and unpacking it. 
A full installation likely looks like::
  
  $ tar xzf KmlMapServer-0.2.tar.gz
  $ cd KmlMapServer
  $ python setup.py install
  ...
  Installed
 
But for CGI use, you don't even need to deploy it. Just go to the next section.
  
The KmlMapServer.cfg configuration file is deployed by setup in python packages directory. 
For more convenience you can either copy it to /etc/
  

RUNNING UNDER CGI
=================

* Permit CGI execution in the KmlMapServer directory.
  For example, if KmlMapServer is to be run with Apache, the
  following must be added in your Apache configuration,   
  where /var/www/tilecache is the directory resulting from
  the code extraction. On Debian, this is typically /usr/lib/cgi-bin.
  
  ::
    ScriptAlias /KmlMapServer/ /home/user/KmlMapServer/KmlMapServer
    <Directory "/home/user/KmlMapServer/KmlMapServer/">
         AllowOverride None
         Options +ExecCGI -MultiViews +SymLinksIfOwnerMatch
         Order allow,deny
         Allow from all
    </Directory>
    

* Visit:
  
  http://example.com/KmlMapServer/?request=list&map=/home/user/mymap.map
  


RUNNING UNDER MOD_PYTHON
========================

The use of a location heading is the best choice :
<Location "/kmlws/">
    SetHandler python-program
    PythonHandler KmlMapServer.Service
    PythonInterpreter kml_map_server
    
    
    PythonOption KmlMapServerConfig /path/to/kmlmapserver.cfg
</Location>

If you used python eggs to install KmlMapServer, don't forget to add

PythonImport /path/to/my/project/egg.py kml_map_server
to your global Apache configuration (outside any Location or VirtualHost block)

    Now test and visit :
    http://example.com/kmlws/?request=list&map=/home/user/mymap.map



CONFIGURATION
=============
KmlMapServer is configured by a config file, defaulting to kmlmapserver.cfg.
There are several parameters to control KmlMapServer layers that are applicable
to all layers:

 temp_dir
     specifies the directory in which all file generation will be done. It must
     be write access for the user who runs KmlMapServer (apache for example)
 map_name
     the default map to use if none is specified in the query string
 max_features
     The maximum of features to put in the kml document. If over, a WMS link
     will be send in the KML.
 map_dir
     the directory in which you store your mapfiles. Setting it here avoids
     to show it in URLs
 wms_url
     the base url to access your wms server. Example : http://example.com/cgi-bin/mapserv
 logo_url
     URL of the logo to be embedded in the KML docs.
 bbox
     the default bbox to be used if none provided (mainly when testing)
 host
     allows you to specify a different host than the one which will be computed from 
     the first call to the service. Useful in some apache configurations, mainly
     when using a Location block with a subfoldered address (ie:www.example.com/services/kmlmapserver)
 
 
MAPFILE SPECIFIC PARAMETERS
===========================
In order to better control your layers access in the mapfile, here are a few options to use
into the LAYER METADATA block :
    KML_ID : mandatory. Indicates which field to use as object's id
    KML_NAME : Indicates which field to use as object's name. If non provided, KML_ID
    will be used instead.
    KML_DESCRIPTION : Html content of the pop-up which opens on object click.
    Example : "<img src='http://example.com/logo.png'/>
        <h1 style='color:#A85F2A;font-size:14px;font-weight:bold;margin:0px;'>
            My object : $[name]</h1>
            <p style='color:#7A3C10;font-family:Verdana,sans-serif;font-size:110%;text-decoration:none;'>
                <a href='http://example.com/details/id=$[name]' target='_blank'>More info</a>
            </p>
       </h1>"
    KML_CLIP : if set to TRUE, the objects will be clipped to the bbox.
             Useful for layers which very large polygons.
    KML_SIMPLIFY : if set to FALSE, no geometric simplification will be done
            on that layer. Else, or if ommited, it applies for polygon layers
            and simplifies the geometries depending on the current scale. Very handy
            for polygons with complicated geometries, or high definition.
    KML_EXTRA_FIELDS : extra set of fields, comma separated, to be included in the KML output.
        Example : "name,adress,x,y"
    KML_MAX_FEATURES : maximum features to be dumped in KML. Goes to WMS network link instead.
        Overrides config file max_features settings for a specific layer.
        

COMMON REQUESTS
===============

1. List of all layers available in the mapfile.
This is the main KML document, which embeds links to layers content
http://www.example.com/kmlws/?request=list&map=mymap.map

2. Only a specific layer
http://www.example.com/kmlws/?request=layer&map=mymap.map&typename=layer_name
you can add the maxpoints parameter to override config map_features settings
and layer KML_MAX_FEATURES settings for a specific request.

  
HINTS & CAVEATS
===============
Some of the mapfile parameters are used to enhanced output:
wms_title : in the web object metadata, used to name the main document. If none, the map's name is used.
wms_title : in the layer's metadata, used to properly name the layer. If none, the layer's name is used.

Expressions handling :
At the moment, not all of the wide range of MapServer expressions patterns are supported. 
If no CLASSITEM is used, only the first CLASS will be dumped to KML
You can use :
1.
       CLASSITEM field 
    and 
       EXPRESSION value (in your class definition)
2. 
       CLASSITEM field
    and
       EXPRESSION ([field] in "201,211,221")
3.
        CLASSITEM field
    and
       EXPRESSION ([field] = 5.0 or [field] = 5.5)
       

