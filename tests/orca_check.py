# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Devin Prater
import sys, types
from orca import extension_loader
ld = extension_loader.get_loader()
sys.modules['orca_user_extension']=types.ModuleType('orca_user_extension'); sys.modules['orca_user_extension'].__path__=[]
import os
path=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'telegram_access')
from orca import debug; debug.debugLevel=debug.LEVEL_WARNING; debug.debugFile=sys.stderr
print('meta', ld.get_metadata(path+'/__init__.py'))
ext = ld._load_from_file(path, 'telegram_access')
print('loaded', type(ext).__name__, ext.VERSION)
print('prefs', [p.key for p in ext.get_preferences()])
print('cmds', [(c.get_name()) for c in ext._get_commands()])

# Fake Atspi tree to drive the monitor and hooks.
class N:
    def __init__(s, role, name='', kids=(), app='TelegramDesktop', active=True):
        s.role,s.name,s.kids,s.app,s.parent,s.active=role,name,list(kids),app,None,active
        for k in s.kids: k.parent=s
    def get_role_name(s): return s.role
    def get_name(s): return s.name
    def get_description(s): return ''
    def get_child_count(s): return len(s.kids)
    def get_child_at_index(s,i): return s.kids[i]
    def get_parent(s): return s.parent
    def get_index_in_parent(s): return s.parent.kids.index(s) if s.parent else -1
    def get_application(s):
        n=s
        while n.parent: n=n.parent
        return n
    def get_state_set(s):
        class SS:
            def contains(_, st): return s.active
        return SS()
def cells(*names): return [N('table cell',x) for x in names]
def item(name, c=('Sender','Message')): return N('list item', name, cells(*c))
inc = lambda t: item(f'Sarah Cat\n{t}\nReceived at 9:00 AM')
mlist = N('list','Messages',[inc('old one'), item('Seen\nMe\nhi\nSent at 8:00 AM',('Seen','Sender','Message'))])
win = N('filler','window',[N('filler','',[mlist])])
app = N('application','TelegramDesktop',[win]); win.parent=app; app.app='TelegramDesktop'
app.get_name=lambda: 'TelegramDesktop'
spoken=[]
ext.controller = types.SimpleNamespace(present_message_internal=lambda m: spoken.append(m) or True, get_current_object_internal=lambda: None)
ext.settings = types.SimpleNamespace(get=lambda k,d=None: d)
ext._find_app = lambda: app
ext._check()                     # discovery + baseline: silent
assert spoken==[], spoken
ext._check()
mlist.kids.append(inc('Build is green.'))
mlist.kids[-1].parent=mlist
ext._check(); print('1 new ->', spoken)
mlist.kids.append(item('Seen\nMe\nthanks\nSent at 9:01 AM',('Seen','Sender','Message'))); mlist.kids[-1].parent=mlist
ext._check(); print('own message ->', spoken)
a,b=inc('first of two'),inc('second of two')
for x in (a,b): mlist.kids.append(x); x.parent=mlist
ext._check(); print('burst ->', spoken)
win.active=False; win.kids[0].active=False
c=inc('while backgrounded'); mlist.kids.append(c); c.parent=mlist
n=len(spoken); ext._check(); print('background spoken:', len(spoken)-n, '(active-only default)')
ext._session_muted=True; win.active=True; win.kids[0].active=True
d=inc('muted'); mlist.kids.append(d); d.parent=mlist
n=len(spoken); ext._check(); print('muted spoken:', len(spoken)-n)
ext.repeat_last_message(); print('repeat ->', spoken[-1])
# Chat switch: whole list replaced -> silent
ext._session_muted=False
mlist.kids[:] = [inc('other chat 1'), inc('other chat 2')]
for k in mlist.kids: k.parent=mlist
n=len(spoken); ext._check(); print('chat switch spoken:', len(spoken)-n)

# Speech hook
from orca.extension import SpeechOutput
btn = N('button','',[], ); pan = N('filler','',[N('text','Search'), btn]); pan.parent=win; win.kids.append(pan)
r = ext.on_speech_output(SpeechOutput('button', btn)); print('unnamed button ->', r)
named = N('button','Info'); named.parent=win
print('named button ->', ext.on_speech_output(SpeechOutput('button', named)))
m = item('Seen\nMe\nhi ⁨x⁩\nSent at 8:00 AM',('Seen','Sender','Message')); m.parent=mlist
print('msg item ->', ext.on_speech_output(SpeechOutput('list item '+m.name, m)))
other = N('button','',[]); other.parent=N('application','Other'); 
print('other app ->', ext.on_speech_output(SpeechOutput('button', other)))

r = ext.on_speech_output(SpeechOutput('button', btn)); print('unnamed button (fixed) ->', r)
ext.settings = types.SimpleNamespace(get=lambda k,d=None: False if k=='label-unnamed-controls' else d)
print('labels off ->', ext.on_speech_output(SpeechOutput('button', btn)))

# --- text-field wrapper ("read only") ---
from orca import object_properties
RO = object_properties.STATE_READ_ONLY_SPEECH
ext.settings = types.SimpleNamespace(get=lambda k,d=None: d)
inner = N('text','Write a message...'); outer = N('text','Write a message...',[inner]); outer.parent=win
for label,o,t in [
  ('wrapper chunk (inner obj)', inner, f'Write a message... {RO} text'),
  ('real field chunk', inner, 'Write a message... text'),
  ('combined', inner, f'Write a message... {RO} text. Write a message... text'),
  ('wrapper as obj', outer, f'Write a message... {RO} text'),
  ('read-only elsewhere', N('text','Plain'), f'Plain {RO} text')]:
    print(label, '->', ext.on_speech_output(SpeechOutput(t, o)))
