import urllib2
import Tkinter as tk
import sys
import ttk
import requests
import json

from ttkHyperlinkLabel import HyperlinkLabel
import myNotebook as nb

from config import appname, applongname, appversion, config
import companion
import plug

this = sys.modules[__name__]
this.msg = " "
this.cmdr = None

def plugin_start():
        print ('EDSCC Plugin Starting')
        return ('EDSCC')

def plugin_end():
    print('Closing')

def cmdr_data(data, is_beta):
	form_data = {
		'_token' : credentials(this.cmdr),
		'data' : json.dumps(data)
			}
	url = "https://edscc.ddns.net/api/edmc.php"
	"""
	Request URl as a POST with the Form URL plus send the Form Data to each entry.
	"""
	try:				
		r = requests.post(url, data=form_data)
		if r.status_code == 200:
			#print ('URL Success')
			this.msg = 'EDSCC Post Success'
		else:
			print ('URL Fail' + str(r.status_code))
			this.msg = 'EDSCC Post Failed'
	except:
		this.msg = 'EDSCC Post Exception'
	return (this.msg)

def plugin_prefs(parent, cmdr, is_beta):

    PADX = 10
    BUTTONX = 12	# indent Checkbuttons and Radiobuttons
    PADY = 2		# close spacing

    frame = nb.Frame(parent)
    frame.columnconfigure(1, weight=1)

    HyperlinkLabel(frame, text='EDSCC', background=nb.Label().cget('background'), url='https://edscc.ddns.net/', underline=True).grid(columnspan=2, padx=PADX, sticky=tk.W)	# Don't translate
    this.log = tk.IntVar(value = config.getint('edscc_out') and 1)
    this.log_button = nb.Checkbutton(frame, text=_('Send flight log and Cmdr status to EDSCC'), variable=this.log, command=prefsvarchanged)
    this.log_button.grid(columnspan=2, padx=BUTTONX, pady=(5,0), sticky=tk.W)

    nb.Label(frame).grid(sticky=tk.W)	# big spacer 
    this.label = HyperlinkLabel(frame, text=_('EDSCC credentials'), background=nb.Label().cget('background'), url='https://edscc.ddns.net/settings-api', underline=True)	# Section heading in settings
    this.label.grid(columnspan=2, padx=PADX, sticky=tk.W)

    this.apikey_label = nb.Label(frame, text=_('API Key'))	# EDSM setting
    this.apikey_label.grid(row=12, padx=PADX, sticky=tk.W)
    this.apikey = nb.Entry(frame)
    this.apikey.grid(row=12, column=1, padx=PADX, pady=PADY, sticky=tk.EW)

    prefs_cmdr_changed(cmdr, is_beta)

    return frame

def prefs_cmdr_changed(cmdr, is_beta):
    this.log_button['state'] = cmdr and not is_beta and tk.NORMAL or tk.DISABLED
    this.apikey['state'] = tk.NORMAL
    this.apikey.delete(0, tk.END)
    if cmdr:
        cred = credentials(cmdr)
        if cred:
            this.apikey.insert(0, cred)
    this.label['state'] = this.apikey_label['state'] = this.apikey['state'] = cmdr and not is_beta and this.log.get() and tk.NORMAL or tk.DISABLED

def prefsvarchanged():
    this.label['state'] = this.apikey_label['state'] = this.apikey['state'] = this.log.get() and this.log_button['state'] or tk.DISABLED

def prefs_changed(cmdr, is_beta):
    changed = config.getint('edscc_out') != this.log.get()
    config.set('edscc_out', this.log.get())

    # Override standard URL functions
    if config.get('system_provider') == 'EDSCC':
        this.system_link['url'] = this.system
    if config.get('station_provider') == 'EDSCC':
        this.station_link['url'] = this.station or this.system

    if cmdr and not is_beta:
        this.cmdr = cmdr
        this.FID = None
        cmdrs = config.get('edscc_cmdrs') or []
        apikeys = config.get('edscc_apikeys') or []
        if cmdr in cmdrs:
            idx = cmdrs.index(cmdr)
            apikeys.extend([''] * (1 + idx - len(apikeys)))
            changed |= (apikeys[idx] != this.apikey.get().strip())
            apikeys[idx] = this.apikey.get().strip()
        else:
            config.set('edscc_cmdrs', cmdrs + [cmdr])
            changed = True
            apikeys.append(this.apikey.get().strip())
        config.set('edscc_apikeys', apikeys)

        if this.log.get() and changed:
            this.newuser = True	# Send basic info at next Journal event
            add_event('getCommanderProfile', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), { 'searchName': cmdr })
            call()

def credentials(cmdr):
    # Credentials for cmdr
    if not cmdr:
        return None

    cmdrs = config.get('edscc_cmdrs') or []
    if cmdr in cmdrs and config.get('edscc_apikeys'):
        return config.get('edscc_apikeys')[cmdrs.index(cmdr)]
    else:
        return None