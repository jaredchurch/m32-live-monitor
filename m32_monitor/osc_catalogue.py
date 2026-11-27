"""Protocol-family catalogue for the M32/X32 OSC simulator.

Patterns describe address families, not a claim that every parameter in each
family is implemented. The support field is intentionally conservative.
"""

OSC_CATALOGUE = [
    {"category":"Connection and discovery","support":"implemented","items":[
        {"pattern":"/info","purpose":"Server version and model identity","operations":"GET"},
        {"pattern":"/xinfo","purpose":"Discovery identity and local IP","operations":"GET"},
        {"pattern":"/status","purpose":"Server availability and identity","operations":"GET"},
        {"pattern":"/xremote","purpose":"Register for unsolicited parameter updates","operations":"COMMAND"},
        {"pattern":"/subscribe","purpose":"Subscribe to individual parameter updates","operations":"COMMAND","note":"Basic client registration is supported; full per-address subscription scheduling is not yet modelled."},
        {"pattern":"/renew","purpose":"Renew active subscriptions","operations":"COMMAND"},
        {"pattern":"/unsubscribe","purpose":"Cancel subscriptions","operations":"COMMAND"}
    ]},
    {"category":"Configuration and stereo linking","support":"partial","items":[
        {"pattern":"/config/chlink/{1-2...31-32}","purpose":"Link/unlink adjacent input-channel pairs","operations":"GET, SET, /node"},
        {"pattern":"/config/auxlink/{1-2...7-8}","purpose":"Link/unlink Aux input pairs","operations":"GET, SET, /node"},
        {"pattern":"/config/fxlink/{1-2...7-8}","purpose":"Link/unlink FX return pairs","operations":"GET, SET, /node"},
        {"pattern":"/config/buslink/{1-2...15-16}","purpose":"Link/unlink mix-bus pairs","operations":"GET, SET, /node"},
        {"pattern":"/config/mtxlink/{1-2...5-6}","purpose":"Link/unlink Matrix pairs","operations":"GET, SET, /node"},
        {"pattern":"/config/mute/{1...6}","purpose":"Mute group state","operations":"GET, SET, /node"},
        {"pattern":"/config/linkcfg/{hadly,eq,dyn,fdrmute}","purpose":"Linked-channel parameter coupling preferences (delay/headamp, EQ, dynamics, fader/mute)","operations":"GET, SET, /node"},
        {"pattern":"/config/solo/*, /config/talk/*, /config/osc/*","purpose":"Solo, talkback and oscillator configuration","operations":"GET, SET","note":"Known protocol families; not yet fully simulated."},
        {"pattern":"/config/mono/{mode,link}","purpose":"Main mono/centre output mode and Main L/R dependency","operations":"GET, SET, /node","note":"Mode and link settings are simulated."},
        {"pattern":"/config/solo/{level,source,sourcetrim,chmode,busmode,dcamode,exclusive,followsel,followsolo,dimatt,dim,mono,delay,delaytime,masterctrl,mute,dimpfl}","purpose":"Solo monitor source, level, PFL/AFL modes, dimming and delay","operations":"GET, SET, /node","note":"All 17 documented solo-monitor fields are simulated."},
        {"pattern":"/config/routing/*","purpose":"Input, AES50, Card, output and playback routing banks","operations":"GET, SET, /node","note":"Routing snapshot covers selected assignments; complete node read/write coverage is outstanding."},
        {"pattern":"/config/userctrl/*, /config/dp48/*","purpose":"User controls and DP48 configuration","operations":"GET, SET, /node","note":"Known protocol families; not yet fully simulated."}
    ]},
    {"category":"Input channels","support":"partial","items":[
        {"pattern":"/ch/{01...32}/config/*","purpose":"Channel name, source, colour and configuration","operations":"GET, SET, /node"},
        {"pattern":"/ch/{01...32}/preamp/*, /ch/{01...32}/delay/*","purpose":"Preamp, phantom/trim and channel delay","operations":"GET, SET, /node","note":"Most processing parameters are not yet modelled."},
        {"pattern":"/ch/{01...32}/gate/*, /ch/{01...32}/dyn/*","purpose":"Gate and dynamics processing","operations":"GET, SET, /node","note":"Not yet fully modelled."},
        {"pattern":"/ch/{01...32}/eq/*","purpose":"Four-band channel equaliser","operations":"GET, SET, /node","note":"Not yet fully modelled."},
        {"pattern":"/ch/{01...32}/insert/*","purpose":"Channel insert assignment","operations":"GET, SET, /node","note":"Not yet fully modelled."},
        {"pattern":"/ch/{01...32}/mix/*","purpose":"Main assignments, fader, mute, pan and 16 bus sends","operations":"GET, SET, /node","note":"Core mute/fader/main-send/bus-send parameters are modelled; others remain gaps."},
        {"pattern":"/ch/{01...32}/grp/*","purpose":"DCA and mute-group assignments","operations":"GET, SET, /node"},
        {"pattern":"/ch/{01...32}/automix/*","purpose":"Automix group and weight","operations":"GET, SET, /node","note":"Known protocol family; not yet simulated."}
    ]},
    {"category":"Aux inputs and FX returns","support":"partial","items":[
        {"pattern":"/auxin/{01...08}/config/*, /auxin/{01...08}/preamp/*","purpose":"Aux input identity and preamp","operations":"GET, SET, /node","note":"Basic strip config is modelled; preamp coverage is incomplete."},
        {"pattern":"/auxin/{01...08}/eq/*, /auxin/{01...08}/mix/*, /auxin/{01...08}/grp/*","purpose":"Aux EQ, sends, main assignment and groups","operations":"GET, SET, /node","note":"Core mute/fader/send/group fields are modelled; remaining fields are gaps."},
        {"pattern":"/fxrtn/{01...08}/config/*, /fxrtn/{01...08}/eq/*","purpose":"FX return identity and equalisation","operations":"GET, SET, /node","note":"Basic strip state is modelled; EQ is not yet fully modelled."},
        {"pattern":"/fxrtn/{01...08}/mix/*, /fxrtn/{01...08}/grp/*","purpose":"FX return fader, mute, sends and groups","operations":"GET, SET, /node","note":"Core mute/fader/send/group fields are modelled."}
    ]},
    {"category":"Buses, matrices and main outputs","support":"partial","items":[
        {"pattern":"/bus/{01...16}/config/*, /bus/{01...16}/mix/*","purpose":"Bus name, processing, fader, mute and sends to matrices","operations":"GET, SET, /node","note":"Core output mute/fader/name and Matrix sends are modelled."},
        {"pattern":"/mtx/{01...06}/config/*, /mtx/{01...06}/mix/*, /mtx/{01...06}/grp/*","purpose":"Matrix output processing, fader, mute and group assignments","operations":"GET, SET, /node","note":"Core name/fader/mute/group fields are modelled."},
        {"pattern":"/main/st/{config,mix,eq,dyn,insert}/*","purpose":"Main stereo output","operations":"GET, SET, /node","note":"Core fader/mute/group/send fields are modelled."},
        {"pattern":"/main/m/{config,mix,eq,dyn,insert}/*","purpose":"Main mono/centre output","operations":"GET, SET, /node","note":"Core fader/mute/group/send fields are modelled."}
    ]},
    {"category":"DCA and mute groups","support":"partial","items":[
        {"pattern":"/dca/{1...8}/{config,mix}/*","purpose":"DCA name, fader and mute","operations":"GET, SET, /node","note":"Core name/fader/mute are modelled."},
        {"pattern":"/config/mute/{1...6}","purpose":"Mute group active state","operations":"GET, SET, /node"},
        {"pattern":"/-prefs/dcamute, /-prefs/hardmute","purpose":"DCA mute and hard-mute behaviour preferences","operations":"GET"}
    ]},
    {"category":"Effects, outputs and headamps","support":"known-unsupported","items":[
        {"pattern":"/fx/{1...8}/*","purpose":"FX rack type, routing and effect parameters","operations":"GET, SET, /node"},
        {"pattern":"/outputs/*","purpose":"Output patching and physical output configuration","operations":"GET, SET, /node"},
        {"pattern":"/headamp/{1...N}","purpose":"Remote headamp gain and phantom state","operations":"GET, SET, /node"},
        {"pattern":"/-insert/*","purpose":"Insert routing and insert device configuration","operations":"GET, SET, /node"}
    ]},
    {"category":"Meters and subscriptions","support":"partial","items":[
        {"pattern":"/meters/{0...16}","purpose":"Meter streams as binary OSC blobs","operations":"SUBSCRIBE","note":"Stream shapes are modelled; values are currently synthetic zeroes."},
        {"pattern":"/batchsubscribe","purpose":"Subscribe to batches of meter values","operations":"COMMAND"},
        {"pattern":"/formatsubscribe","purpose":"Subscribe to packed groups of parameter values","operations":"COMMAND"},
        {"pattern":"/renew, /unsubscribe","purpose":"Maintain or cancel meter/format subscriptions","operations":"COMMAND"}
    ]},
    {"category":"Scenes, shows, snippets and libraries","support":"known-unsupported","items":[
        {"pattern":"/-show, /showdump, /-showfile/*","purpose":"Show metadata and show-file transfer","operations":"COMMAND, /node","note":"Only the empty-show response is currently stubbed; no show data is stored."},
        {"pattern":"/-libs/*","purpose":"Preset/library browsing and management","operations":"GET, SET, /node"},
        {"pattern":"/add, /copy, /save, /load, /delete, /rename","purpose":"Scene, snippet, preset and dataset operations","operations":"COMMAND"}
    ]},
    {"category":"Preferences, USB and status","support":"partial","items":[
        {"pattern":"/-prefs/rta/*","purpose":"RTA visibility, gain, source, mode, detector, decay and options","operations":"GET, SET, /node"},
        {"pattern":"/-prefs/card/*","purpose":"Card, USB, ADAT, MADI and X-Live recorder preferences","operations":"GET, /node"},
        {"pattern":"/-prefs/*","purpose":"Other console preferences","operations":"GET, SET, /node","note":"Only selected RTA, card, DCA-mute and hard-mute fields are modelled."},
        {"pattern":"/-usb/*","purpose":"USB recorder/player state and metadata","operations":"GET, SET, /node","note":"Known protocol family; not yet simulated."},
        {"pattern":"/-stat/*","purpose":"Console status, solo, RTA, AES50 and recorder status","operations":"GET, /node","note":"Selected solo, RTA and UREC status fields are modelled."},
        {"pattern":"/-urec/*, /-stat/urec/*","purpose":"X-Live SD recorder, sessions, markers and transport status","operations":"GET, /node"}
    ]},
    {"category":"Additional documented node families","support":"known-unsupported","items":[
        {"pattern":"/config/userout/{in,out}/{01...48}","purpose":"User-defined input/output routing maps","operations":"GET, SET, /node"},
        {"pattern":"/config/userctrl/{A,B,C}/*","purpose":"User-assignment banks, encoder and button assignments","operations":"GET, SET, /node"},
        {"pattern":"/config/tape, /config/amixenable","purpose":"Tape and automix enable configuration","operations":"GET, SET, /node"},
        {"pattern":"/config/dp48/*","purpose":"DP48 personal monitor assignment, links and group names","operations":"GET, SET, /node"},
        {"pattern":"/ch/{01...32}/gate/filter, /ch/{01...32}/dyn/filter","purpose":"Gate and dynamics side-chain filter parameters","operations":"GET, SET, /node"},
        {"pattern":"/auxin/{01...08}/eq/{1...4}, /fxrtn/{01...08}/eq/{1...4}","purpose":"Individual EQ band parameters","operations":"GET, SET, /node"},
        {"pattern":"/bus/{01...16}/{dyn,eq,insert}/*","purpose":"Bus dynamics, EQ and insert processing","operations":"GET, SET, /node"},
        {"pattern":"/mtx/{01...06}/{preamp,dyn,insert,eq}/*","purpose":"Matrix preamp, dynamics, insert and EQ processing","operations":"GET, SET, /node"},
        {"pattern":"/dca/{1...8}/config","purpose":"DCA configuration node","operations":"GET, SET, /node"},
        {"pattern":"/fx/{1...8}/{source,par}/*","purpose":"Effects rack source and up to 64 effect parameters","operations":"GET, SET, /node"},
        {"pattern":"/outputs/main/{01...16}/*, /outputs/aux/{01...06}/*","purpose":"Main and Aux physical output assignments","operations":"GET, SET, /node"},
        {"pattern":"/outputs/p16/{01...16}/*, /outputs/aes/{01...02}/*, /outputs/rec/{01...02}/*","purpose":"P16, AES and recording output assignments","operations":"GET, SET, /node"},
        {"pattern":"/headamp/{000...127}","purpose":"Headamp gain and phantom configuration","operations":"GET, SET, /node"},
        {"pattern":"/-show/showfile/{inputs,mxsends,mxbuses,console,chan16,chan32,return,buses,effects,cue,scene,snippet}","purpose":"Show file content and cue/scene/snippet indexes","operations":"GET, SET, /node"},
        {"pattern":"/-libs/{ch,fx,r,mon}/{001...100}/*","purpose":"Channel, FX, routing and monitor preset libraries","operations":"GET, SET, /node"},
        {"pattern":"/-prefs/{style,bright,lcdcont,ledbright,lamp,clock*,confirm*,scene_advance,safe_masterlevels,autosel,show_control,fastFaders,ip,remote,iQ,key}/*","purpose":"Console preferences, networking, remote control, Turbosound iQ and key assignments","operations":"GET, SET, /node"},
        {"pattern":"/-usb/{path,title,dir,dirpos,maxpos,dir/{000...999}/*}","purpose":"USB player/recorder file browser and metadata","operations":"GET, SET, /node"},
        {"pattern":"/-stat/{selidx,chfaderbank,grpfaderbank,sendsonfader,bussenbank,eqband,userbank,autosave,lock,usbmounted,remote,xcardtype,xcardsync,geq*,screen*,aes50*,solosw*,talk*,osc*,tape*}","purpose":"Surface, screen, AES50, solo, talkback, oscillator and tape status","operations":"GET, /node"}
    ]},
    {"category":"Additional documented X32node headers","support":"known-unsupported","items":[
        {"pattern":"/config/routing/routswitch, /config/routing/PLAY","purpose":"Routing record/playback switch and playback source banks","operations":"/node, GET, SET"},
        {"pattern":"/config/userout/in/{01...32}, /config/userout/out/{01...48}","purpose":"User-defined input and output routing assignments","operations":"/node, GET, SET"},
        {"pattern":"/config/dp48, /config/dp48/assign, /config/dp48/grpname","purpose":"DP48 personal-monitor assignments, links and group names","operations":"/node, GET, SET"},
        {"pattern":"/config/amixenable","purpose":"Automix enable configuration","operations":"/node, GET, SET"},
        {"pattern":"/-show/prepos, /-show/prepos/current","purpose":"Show-file preposition and current show position","operations":"/node, GET"},
        {"pattern":"/-prefs/iq, /-prefs/iq/{01...16}","purpose":"Turbosound iQ speaker preferences","operations":"/node, GET, SET"},
        {"pattern":"/outputs/p16/{01...16}/iQ","purpose":"P16 output speaker metadata and iQ control","operations":"/node, GET, SET"},
        {"pattern":"/-stat/screen/*, /-stat/screen/*/page","purpose":"Surface screen, selected page and display state","operations":"/node, GET"},
        {"pattern":"/-stat/tape/*, /-stat/aes50/*","purpose":"USB/tape transport and AES50 link state","operations":"/node, GET"},
        {"pattern":"/-stat/solosw/{01...80}","purpose":"Solo-switch status across channels, buses, matrices and DCAs","operations":"/node, GET"},
        {"pattern":"/-libs/{ch,fx,r,mon}/{001...100}/*","purpose":"Channel, effects, routing and monitor preset metadata","operations":"/node, GET, SET"}
    ]},
    {"category":"Actions and undo","support":"known-unsupported","items":[
        {"pattern":"/-action/*","purpose":"Console action and surface control events","operations":"COMMAND"},
        {"pattern":"/-undo/*","purpose":"Undo history and action control","operations":"COMMAND"}
    ]}
]

OSC_COMMANDS = [
    {"address":"/info","purpose":"Identify server version/model"},
    {"address":"/xinfo","purpose":"Discovery identity response"},
    {"address":"/status","purpose":"Server status response"},
    {"address":"/xremote","purpose":"Register for parameter change notifications"},
    {"address":"/subscribe","purpose":"Subscribe to individual parameter updates"},
    {"address":"/formatsubscribe","purpose":"Subscribe to packed parameter groups"},
    {"address":"/batchsubscribe","purpose":"Subscribe to meter or packed data streams"},
    {"address":"/renew","purpose":"Renew active subscriptions"},
    {"address":"/unsubscribe","purpose":"Cancel active subscriptions"},
    {"address":"/node","purpose":"Read an X32node group as a text response"},
    {"address":"/","purpose":"Write X32node text data"},
    {"address":"/showdump","purpose":"Request show metadata"},
    {"address":"/-action/*, /-undo/*","purpose":"Console action and undo command families"},
    {"address":"/add, /copy, /save, /load, /delete, /rename","purpose":"Dataset and scene/library management"}
]


def catalogue_snapshot():
    categories = []
    for category in OSC_CATALOGUE:
        categories.append({**category, "items": [dict(item) for item in category["items"]]})
    return {"protocol_reference":"Unofficial X32/M32 OSC Remote Protocol, firmware 4.0+ (community-maintained)",
            "catalogue_scope":"Address families and client/server command classes; patterns expand to many individual addresses.",
            "categories":categories, "commands":[dict(item) for item in OSC_COMMANDS],
            "support_levels":[
                {"id":"implemented","label":"Implemented","description":"Simulator has a response/state handler for this operation or family."},
                {"id":"partial","label":"Partially implemented","description":"Some addresses or behaviours are supported; inspect the notes and test with M32-Edit."},
                {"id":"known-unsupported","label":"Known / not implemented","description":"Documented protocol family, but simulator support has not yet been built."}
            ]}
