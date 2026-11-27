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
        {"pattern":"/config/mono/{mode,link}","purpose":"Main mono/centre output mode and Main L/R dependency","operations":"GET, SET, /node","note":"Mode and link settings are simulated."},
        {"pattern":"/config/solo/{level,source,sourcetrim,chmode,busmode,dcamode,exclusive,followsel,followsolo,dimatt,dim,mono,delay,delaytime,masterctrl,mute,dimpfl}","purpose":"Solo monitor source, level, PFL/AFL modes, dimming and delay","operations":"GET, SET, /node","note":"All 17 documented solo-monitor fields are simulated."},
        {"pattern":"/config/talk/{enable,source}, /config/talk/{A,B}/{level,dim,latch,destmap}","purpose":"Talkback enable, source, A/B levels, dim/latch and destination routing masks","operations":"GET, SET, /node","note":"Shared, A and B node reads/writes plus individual field access are simulated."},
        {"pattern":"/config/osc/{level,f1,f2,fsel,type,dest}","purpose":"Oscillator generator level, frequency selection, waveform and output destination","operations":"GET, SET, /node","note":"All six documented fields support validated individual access and grouped X32node reads/writes."},
        {"pattern":"/config/routing/*","purpose":"Input, AES50, Card, output and playback routing banks","operations":"GET, SET, /node","note":"Documented bank node reads and validated individual assignments are supported; the parent config/routing aggregate is a simulator convenience, not a documented header."},
        {"pattern":"/config/userctrl/{A,B,C}/*","purpose":"User-assignment bank colours, four encoders and eight buttons per bank","operations":"GET, SET, /node","note":"Implemented: bank, encoder and button group reads/writes; individual colour and string values are validated."}
    ]},
    {"category":"Input channels","support":"partial","items":[
        {"pattern":"/ch/{01...32}/config/*","purpose":"Channel name, icon, source and colour configuration","operations":"GET, SET, /node","note":"Documented channel config node is modelled with validated name, icon, colour and source values."},
        {"pattern":"/ch/{01...32}/preamp/*, /ch/{01...32}/delay/*","purpose":"Preamp trim, polarity, low-cut/phantom controls and channel delay","operations":"GET, SET, /node","note":"Documented delay and preamp nodes, grouped reads/writes and individual fields are simulated with range validation."},
        {"pattern":"/ch/{01...32}/gate/*, /ch/{01...32}/dyn/*","purpose":"Gate, side-chain filter, compressor/expander and dynamics filter","operations":"GET, SET, /node","note":"Documented gate/dynamics nodes and filter subnodes support grouped reads/writes and validated individual fields."},
        {"pattern":"/ch/{01...32}/eq/*","purpose":"Four-band channel equaliser and individual band parameters","operations":"GET, SET, /node","note":"EQ enable and all four bands (type, frequency, gain and Q) support grouped reads/writes and individual access."},
        {"pattern":"/ch/{01...32}/insert/*","purpose":"Channel insert enable, position and FX/Aux selection","operations":"GET, SET, /node","note":"Documented insert node supports grouped reads/writes and validated individual fields."},
        {"pattern":"/ch/{01...32}/mix/*","purpose":"Main assignments, fader, mute, pan and 16 bus sends","operations":"GET, SET, /node","note":"Parent mix and 16 send nodes are modelled, including send pan, tap type and pan-follow fields where documented."},
        {"pattern":"/ch/{01...32}/grp/*","purpose":"DCA and mute-group assignments","operations":"GET, SET, /node"},
        {"pattern":"/ch/{01...32}/automix/*","purpose":"Automix group assignment and weight","operations":"GET, SET, /node","note":"Group and weight are modelled for channel strips; firmware behaviour restricts effective automix use to channels 01–08."}
    ]},
    {"category":"Aux inputs and FX returns","support":"partial","items":[
        {"pattern":"/auxin/{01...08}/config/*, /auxin/{01...08}/preamp/*","purpose":"Aux input identity and preamp trim/polarity","operations":"GET, SET, /node","note":"Documented config and preamp nodes are modelled with grouped reads/writes and validated fields."},
        {"pattern":"/auxin/{01...08}/eq/*, /auxin/{01...08}/mix/*, /auxin/{01...08}/grp/*","purpose":"Aux EQ, sends, main assignment and groups","operations":"GET, SET, /node","note":"Documented EQ (four bands), mix, send and group nodes are modelled. No Aux gate/dynamics/delay/insert node is listed in the reference."},
        {"pattern":"/fxrtn/{01...08}/config/*, /fxrtn/{01...08}/eq/*","purpose":"FX return identity and four-band equalisation","operations":"GET, SET, /node","note":"Documented config and EQ nodes, including all four bands, are modelled. No FX return preamp/gate/dynamics/delay/insert node is listed in the reference."},
        {"pattern":"/fxrtn/{01...08}/mix/*, /fxrtn/{01...08}/grp/*","purpose":"FX return fader, mute, sends and groups","operations":"GET, SET, /node","note":"Documented parent mix, send and group nodes are modelled."}
    ]},
    {"category":"Buses, matrices and main outputs","support":"partial","items":[
        {"pattern":"/bus/{01...16}/config/*, /bus/{01...16}/mix/*","purpose":"Bus name, processing, fader, mute and sends to matrices","operations":"GET, SET, /node","note":"Bus config node returns name, icon and colour; core output mute/fader and Matrix sends are modelled."},
        {"pattern":"/mtx/{01...06}/config/*, /mtx/{01...06}/mix/*, /mtx/{01...06}/grp/*","purpose":"Matrix output configuration, fader, mute and group assignments","operations":"GET, SET, /node","note":"Implemented: config discovery (name/icon/colour), documented config/preamp/invert alias, output fader/mute and DCA/mute-group assignments."},
        {"pattern":"/main/st/{config,dyn,dyn/filter,insert,eq,eq/{1...6},mix,grp}/*","purpose":"Main stereo output processing and control","operations":"GET, SET, /node","note":"Implemented config, dynamics/filter, insert, six-band EQ, fader/mute and group fields."},
        {"pattern":"/main/m/{config,dyn,dyn/filter,insert,eq,eq/{1...6},mix,grp}/*","purpose":"Main mono/centre output processing and control","operations":"GET, SET, /node","note":"Implemented config, dynamics/filter, insert, six-band EQ, fader/mute and group fields."}
    ]},
    {"category":"DCA and mute groups","support":"partial","items":[
        {"pattern":"/dca/{1...8}, /dca/{1...8}/config, /dca/{1...8}/{on,fader,config/{name,icon,color}}","purpose":"DCA on/off, fader and configuration (name, icon and colour)","operations":"GET, SET, /node","note":"Implemented for all eight DCAs: complete parent and config node reads/writes, individual parameter access and range validation."},
        {"pattern":"/config/mute/{1...6}","purpose":"Mute group active state","operations":"GET, SET, /node"},
        {"pattern":"/-prefs/dcamute, /-prefs/hardmute","purpose":"DCA mute and hard-mute behaviour preferences","operations":"GET"}
    ]},
    {"category":"Effects, outputs and headamps","support":"partial","items":[
        {"pattern":"/fx/{1...8}, /fx/{1...8}/type, /fx/{1...4}/source/{l,r}, /fx/{1...8}/par/{01...64}","purpose":"FX rack effect type, stereo source routing and 64 effect parameters","operations":"GET, SET, /node","note":"Implemented across all eight slots. Slots 1-4 support effect types 0-60 and stereo source L/R; slots 5-8 support their restricted effect list 0-33 and have no source node. All slots expose 64 stored parameter values."},
        {"pattern":"/outputs/main/{01...16}, /outputs/main/{01...16}/delay","purpose":"Sixteen physical main output patches: source, tap position, polarity and delay","operations":"GET, SET, /node","note":"Implemented: grouped and individual reads/writes with source, tap-position and delay validation."},
        {"pattern":"/outputs/aux/{01...06}","purpose":"Six physical auxiliary output patches: source, tap position and polarity","operations":"GET, SET, /node","note":"Implemented: grouped and individual reads/writes with source, tap-position and polarity validation."},
        {"pattern":"/outputs/p16/{01...16}, /outputs/p16/{01...16}/iQ","purpose":"Sixteen Ultranet/P16 personal-monitor output assignments and optional Turbosound iQ speaker configuration","operations":"GET, SET, /node","note":"Implemented: source and tap-position assignments plus iQ group and speaker settings."},
        {"pattern":"/outputs/aes/{01...02}","purpose":"Two AES50 output banks: source, tap position and polarity","operations":"GET, SET, /node","note":"Implemented grouped and individual reads/writes with source, tap-position and polarity validation."},
        {"pattern":"/outputs/rec/{01...02}","purpose":"Two recording-card output banks: source and tap position","operations":"GET, SET, /node","note":"Implemented grouped and individual reads/writes with source and tap-position validation."},
        {"pattern":"/headamp/{000...127}, /headamp/{000...127}/{gain,phantom}","purpose":"Remote headamp gain (-12 to +60 dB in 0.5 dB steps) and phantom power","operations":"GET, SET, /node","note":"Implemented for all 128 headamps: local XLR inputs 000-031, AES50 A 032-079 and AES50 B 080-127."},
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
        {"pattern":"/config/userrout/out, /config/userrout/in, /config/userrout/{out/{01...48},in/{01...32}}","purpose":"User-defined output and input routing source assignments","operations":"GET, SET, /node","note":"Implemented: 48 output and 32 input slots; individual writes and ordered bulk writes with integer source validation."},
        {"pattern":"/config/routing, /config/routing/{IN,AES50A,AES50B,CARD,OUT,PLAY}","purpose":"Grouped input, AES50, Card, output and playback patch configuration","operations":"GET, SET, /node","note":"Implemented: parent and bank-group reads plus ordered grouped writes; unreceived values default to 0 in the simulator."},
        {"pattern":"/config/userctrl/{A,B,C}/*","purpose":"User-assignment banks, encoder and button assignments","operations":"GET, SET, /node"},
        {"pattern":"/config/tape, /config/amixenable","purpose":"Tape gains/play mode and automix group X/Y enable flags","operations":"GET, SET, /node","note":"Implemented: grouped reads/writes and validated individual updates."},
        {"pattern":"/config/dp48/{scope,broadcast,aesAB,link,assign,grpname}","purpose":"DP48 personal monitor scope, broadcast, AES50 target, channel links, group assignments and names","operations":"GET, SET, /node","note":"Implemented: parent and link/assign/group-name node reads/writes plus validated individual updates."},
        {"pattern":"/ch/{01...32}/gate/filter, /ch/{01...32}/dyn/filter","purpose":"Gate and dynamics side-chain filter parameters","operations":"GET, SET, /node"},
        {"pattern":"/auxin/{01...08}/eq/{1...4}, /fxrtn/{01...08}/eq/{1...4}","purpose":"Individual EQ band parameters","operations":"GET, SET, /node"},
        {"pattern":"/bus/{01...16}/dyn, /bus/{01...16}/dyn/filter","purpose":"Bus dynamics and side-chain filter processing parameters","operations":"GET, SET, /node","note":"Implemented: dynamics and side-chain filter fields."},
        {"pattern":"/bus/{01...16}/insert","purpose":"Bus insert enable, position and FX/Aux selection","operations":"GET, SET, /node","note":"Implemented: grouped and individual validated fields."},
        {"pattern":"/bus/{01...16}/eq, /bus/{01...16}/eq/{1...6}","purpose":"Bus EQ enable and six parametric EQ bands","operations":"GET, SET, /node","note":"Implemented: grouped and individual access for all six bands."},
        {"pattern":"/bus/{01...16}/mix, /bus/{01...16}/mix/{01...06}, /bus/{01...16}/grp","purpose":"Bus output fader/mute, six Matrix sends and DCA/mute-group assignments","operations":"GET, SET, /node","note":"Implemented: parent mix, matrix sends and group nodes."},
        {"pattern":"/mtx/{01...06}/{preamp,dyn,dyn/filter,insert,eq,eq/{1...6}}/*","purpose":"Matrix polarity, dynamics and side-chain filter, insert and six-band EQ processing","operations":"GET, SET, /node","note":"Implemented: grouped nodes, individual fields and validated writes across all six matrices."},
        {"pattern":"/main/{st,m}/mix/{01...06}","purpose":"Main L/R and Mono/Centre sends to Matrix outputs","operations":"GET, SET, /node","note":"Implemented: six validated Matrix sends for each main output."},
        {"pattern":"/dca/{1...8}/config","purpose":"DCA configuration node","operations":"GET, SET, /node"},
        {"pattern":"/fx/{1...8}/{source,par}/*","purpose":"Effects rack source and up to 64 effect parameters","operations":"GET, SET, /node"},
        {"pattern":"/outputs/main/{01...16}/*, /outputs/aux/{01...06}/*","purpose":"Main and Aux physical output assignments","operations":"GET, SET, /node"},
        {"pattern":"/outputs/p16/{01...16}/*, /outputs/aes/{01...02}/*, /outputs/rec/{01...02}/*","purpose":"P16, AES and recording output assignments","operations":"GET, SET, /node"},
        {"pattern":"/headamp/{000...127}, /headamp/{000...127}/{gain,phantom}","purpose":"Headamp gain and phantom configuration","operations":"GET, SET, /node","note":"Implemented for all 128 headamps with range and step validation."},
        {"pattern":"/-show/showfile/{inputs,mxsends,mxbuses,console,chan16,chan32,return,buses,effects,cue,scene,snippet}","purpose":"Show file content and cue/scene/snippet indexes","operations":"GET, SET, /node"},
        {"pattern":"/-libs/{ch,fx,r,mon}/{001...100}/*","purpose":"Channel, FX, routing and monitor preset libraries","operations":"GET, SET, /node"},
        {"pattern":"/-prefs/{style,bright,lcdcont,ledbright,lamp,clock*,confirm*,scene_advance,safe_masterlevels,autosel,show_control,fastFaders,ip,remote,iQ,key}/*","purpose":"Console preferences, networking, remote control, Turbosound iQ and key assignments","operations":"GET, SET, /node"},
        {"pattern":"/-usb/{path,title,dir,dirpos,maxpos,dir/{000...999}/*}","purpose":"USB player/recorder file browser and metadata","operations":"GET, SET, /node"},
        {"pattern":"/-stat/{selidx,chfaderbank,grpfaderbank,sendsonfader,bussenbank,eqband,userbank,autosave,lock,usbmounted,remote,xcardtype,xcardsync,geq*,screen*,aes50*,solosw*,talk*,osc*,tape*}","purpose":"Surface, screen, AES50, solo, talkback, oscillator and tape status","operations":"GET, /node"}
    ]},
    {"category":"Additional documented X32node headers","support":"known-unsupported","items":[
        {"pattern":"/config/routing/{routswitch,rootswitch}, /config/routing/PLAY","purpose":"Routing record/playback switch aliases and playback source banks","operations":"/node, GET, SET","note":"Both documented switch spellings are accepted; routing enum writes are range-checked in simulator mode."},
        {"pattern":"/config/userrout/in/{01...32}","purpose":"User-defined input routing assignments","operations":"/node, GET, SET","note":"Implemented: all 32 input slots; integer sources 0-168."},
        {"pattern":"/config/dp48, /config/dp48/assign, /config/dp48/link, /config/dp48/grpname","purpose":"DP48 scope, broadcast, AES50 target, links, assignments and group names","operations":"/node, GET, SET","note":"Implemented: parent and sub-node reads, grouped writes and validated individual values."},
        {"pattern":"/config/amixenable/{X,Y}","purpose":"Automix enable flags for groups X and Y","operations":"/node, GET, SET","note":"Implemented: grouped and individual access."},
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
