from jabberbot import botcmd
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import time
import re
import requests
import json
import calendar
import base64
import vmbot_config as vmc


class EveUtils(object):
    access_token = ''
    token_expiry = 0
    cache_version = 1

    @botcmd
    def price(self, mess, args):
        '''<item name>@[system name] - Displays price of item in Jita or given system (Autocompletion can be disabled by enclosing item/system name in quotes)'''
        autocompleteItem = True
        autocompleteSystem = True
        args = [item.strip() for item in args.strip().split('@')]
        if (len(args) < 1 or len(args) > 2 or args[0] == ''):
            return 'Please specify one item name and optional one system name: <item name>@[system name]'
        if (args[0] in ('plex','Plex','PLEX','Pilot License Extension','Pilot\'s License Extension')):
            args[0] = '30 Day Pilot\'s License Extension (PLEX)'
        if (args[0].startswith('"') and args[0].endswith('"')):
            args[0] = args[0].strip('"')
            autocompleteItem = False
        if (len(args) == 1 or args[1] == ''):
            args.append('Jita')
        if (args[1].startswith('"') and args[1].endswith('"')):
            args[1] = args[1].strip('"')
            autocompleteSystem = False
        item = args[0]
        system = args[1]

        conn = sqlite3.connect('staticdata.sqlite')
        cur = conn.cursor()
        if (autocompleteSystem):
            cur.execute("SELECT regionID, solarSystemID, solarSystemName FROM mapSolarSystems "
                        "WHERE solarSystemName LIKE :name;", {'name' : '%'+system+'%'})
        else:
            cur.execute("SELECT regionID, solarSystemID, solarSystemName FROM mapSolarSystems "
                        "WHERE UPPER(solarSystemName) = UPPER(:name);", {'name' : system})
        systems = cur.fetchall()
        if (len(systems) < 1):
            return 'Can\'t find a matching system!'
        if (autocompleteItem):
            cur.execute("SELECT typeID, typeName FROM invTypes "
                        "WHERE typeName LIKE :name AND marketGroupID IS NOT NULL "
                        "AND marketGroupID < 100000;", {'name' : '%'+item+'%'})
        else:
            cur.execute("SELECT typeID, typeName FROM invTypes "
                        "WHERE UPPER(typeName) = UPPER(:name);", {'name' : item})
        items = cur.fetchall()
        if (len(items) < 1):
            return 'Can\'t find a matching item!'
        cur.close()
        conn.close()

        item = items[0]
        system = systems[0]

        if (self.token_expiry < time.time()):
            self.getAccessToken()

        # Sell
        try:
            r = requests.get('https://crest-tq.eveonline.com/market/'+ str(system[0]) +'/orders/sell/'
                             '?type=https://crest-tq.eveonline.com/types/'+ str(item[0]) +'/',
                             headers={'Authorization' : 'Bearer '+self.access_token, 'User-Agent' : 'VM JabberBot'}, timeout=5)
        except requests.exceptions.RequestException as e:
            return 'There is a problem with the API server. Can\'t connect to the server.<br />' + str(e)
        if (r.status_code != 200):
            return 'The CREST-API returned error code <b>' + str(r.status_code) + '</b>.'
        res = r.json()

        sellvolume = sum([order['volume'] for order in res['items'] if order['location']['name'].startswith(system[2])])
        try:
            sellprice = min([order['price'] for order in res['items'] if order['location']['name'].startswith(system[2])])
        except ValueError:
            sellprice = 0

        # Buy
        try:
            r = requests.get('https://crest-tq.eveonline.com/market/'+ str(system[0]) +'/orders/buy/'
                             '?type=https://crest-tq.eveonline.com/types/'+ str(item[0]) +'/',
                             headers={'Authorization' : 'Bearer '+self.access_token, 'User-Agent' : 'VM JabberBot'}, timeout=5)
        except requests.exceptions.RequestException as e:
            return 'There is a problem with the API server. Can\'t connect to the server.<br />' + str(e)
        if (r.status_code != 200):
            return 'The CREST-API returned error code <b>' + str(r.status_code) + '</b>.'
        res = r.json()

        buyvolume = sum([order['volume'] for order in res['items'] if order['location']['name'].startswith(system[2])])
        try:
            buyprice = max([order['price'] for order in res['items'] if order['location']['name'].startswith(system[2])])
        except ValueError:
            buyprice = 0

        reply = item[1] + ' in ' + system[2] + ':<br />'
        reply += '<b>Sells</b> Price: <b>{:,.2f}</b> ISK. Volume: {:,} units<br />'.format(float(sellprice), int(sellvolume))
        reply += '<b>Buys</b> Price: <b>{:,.2f}</b> ISK. Volume: {:,} units'.format(float(buyprice), int(buyvolume))
        if (sellprice != 0):
            reply += '<br />Spread: {:,.2%}'.format((float(sellprice)-float(buyprice))/float(sellprice)) # (Sell-Buy)/Sell
        if (len(items)>1):
            reply += '<br />Other Item(s) like "' + args[0] + '": ' + items[1][1] + '<br/>'
            if (len(items)>3):
                for item in items[2:4]:
                    reply += item[1] + '<br/>'
            reply += 'Total of <b>' + str(len(items)) + ' Item(s)</b> and <b>' + str(len(systems)) + ' System(s)</b> found.'
        return reply

    @botcmd
    def character(self, mess, args):
        '''<character name> - Displays Corporation, Alliance, Faction, SecStatus and Employment History of a single character
        <character name,character name,character name,...> Displays Corporation, Alliance and Faction of multiple characters'''
        try:
            args = [item.strip() for item in args.strip().split(',')]
            if (args[0] == ''):
                return 'Please provide character name(s), separated by commas'
            if (len(args) > 10):
                return 'Please limit your search to 10 characters at once'
            reply = ''
            cached = self.getCache('https://api.eveonline.com/eve/CharacterID.xml.aspx', params={'names' : ','.join(map(str, args))})
            if (not cached):
                r = requests.post('https://api.eveonline.com/eve/CharacterID.xml.aspx', data={'names' : ','.join(map(str, args))}, headers={ 'User-Agent' : 'VM JabberBot'}, timeout=3)
                if (r.status_code != 200 or r.encoding != 'utf-8'):
                    return 'The CharacterID-API returned error code <b>' + str(r.status_code) + '</b> or the XML encoding is broken.'
                xml = ET.fromstring(r.text)
                self.setCache('https://api.eveonline.com/eve/CharacterID.xml.aspx', doc=str(r.text), expiry=int(calendar.timegm(time.strptime(xml[2].text, '%Y-%m-%d %H:%M:%S'))), params={'names' : ','.join(map(str, args))})
            else:
                xml = ET.fromstring(cached)
            args = []
            for character in xml[1][0]:
                if (int(character.attrib['characterID']) != 0):
                    args.append(character.attrib['characterID'])
                else:
                    reply += 'Character <b>' + character.attrib['name'] + '</b> does not exist<br />'
            if (len(args) == 0):
                return 'None of these character(s) exist'
            cached = self.getCache('https://api.eveonline.com/eve/CharacterAffiliation.xml.aspx', params={'ids' : ','.join(map(str, args))})
            if (not cached):
                r = requests.post('https://api.eveonline.com/eve/CharacterAffiliation.xml.aspx', data={'ids' : ','.join(map(str, args))}, headers={ 'User-Agent' : 'VM JabberBot'}, timeout=4)
                if (r.status_code != 200 or r.encoding != 'utf-8'):
                    return 'The CharacterAffiliation-API returned error code <b>' + str(r.status_code) + '</b> or the XML encoding is broken.'
                xml = ET.fromstring(r.text)
                self.setCache('https://api.eveonline.com/eve/CharacterAffiliation.xml.aspx', doc=str(r.text), expiry=int(calendar.timegm(time.strptime(xml[2].text, '%Y-%m-%d %H:%M:%S'))), params={'ids' : ','.join(map(str, args))})
            else:
                xml = ET.fromstring(cached)
            for row in xml[1][0]:
                character = row.attrib
                reply += str(character['characterName']) + ' is in corporation <b>' + str(character['corporationName']) + '</b>' + ((' in alliance <b>' + str(character['allianceName']) + '</b>') if str(character['allianceName']) != '' else '') + ((' in faction <b>' + str(character['factionName']) + '</b>') if str(character['factionName']) != '' else '') + '<br />'
            if (len(args) == 1):
                r = requests.get('http://evewho.com/api.php', params={'type' : 'character', 'id' : args[0]}, headers={ 'User-Agent' : 'VM JabberBot'}, timeout=5)
                if (r.status_code != 200):
                    return 'The EVEWho-API returned error code <b>' + str(r.status_code) + '</b>.'
                evewhoapi = r.json()
                if (evewhoapi['info'] == None):
                    reply += 'Eve Who got no data for this character<br />'
                else:
                    reply += 'Security status: <b>' + str(evewhoapi['info']['sec_status']) + '</b><br />'
                    corporations = []
                    for corp in evewhoapi['history'][-10:]:
                        corporations.append(corp['corporation_id'])
                    corporations = list(set(corporations))
                    cached = self.getCache('https://api.eveonline.com/eve/charactername.xml.aspx', params={'ids' : ','.join(map(str, corporations))})
                    if (not cached):
                        r = requests.post('https://api.eveonline.com/eve/charactername.xml.aspx', data={'ids' : ','.join(map(str, corporations))}, timeout=3)
                        if (r.status_code != 200 or r.encoding != 'utf-8'):
                            return 'The CharacterAffiliation-API returned error code <b>' + str(r.status_code) + '</b> or the XML encoding is broken.'
                        xml = ET.fromstring(r.text)
                        self.setCache('https://api.eveonline.com/eve/charactername.xml.aspx', doc=str(r.text), expiry=int(calendar.timegm(time.strptime(xml[2].text, '%Y-%m-%d %H:%M:%S'))), params={'ids' : ','.join(map(str, corporations))})
                    else:
                        xml = ET.fromstring(cached)
                    corporations = {}
                    for corp in xml[1][0]:
                        corporations[corp.attrib['characterID']] = corp.attrib['name']
                    for corp in evewhoapi['history'][-10:]:
                        reply += 'From ' + str(corp['start_date']) + ' til ' + (str(corp['end_date']) if str(corp['end_date']) != 'None' else 'now') + ' in <b>' + str(corporations[corp['corporation_id']]) + '</b><br />'
                    if (len(evewhoapi['history']) > 10):
                        reply += 'The full history is available under http://evewho.com/pilot/' + str(evewhoapi['info']['name'].replace(' ', '+')) + '/<br />'
            reply = reply[:-6]
        except requests.exceptions.RequestException as e:
            return 'There is a problem with the API server. Can\'t connect to the server.'
        return reply


    @botcmd
    def route(self, mess, args):
        '''<start system> <destination system> - Calculates the shortest route (experimental). System names are case-sensitive. Do not  spam this with wrong system names or EVE-Central will ban the server.'''
        try:
            args = args.strip().split()
            if (len(args) != 2):
                return 'You need to provide exactly 2 parameters: <start system> <destination system>'
            cached = self.getCache('http://api.eve-central.com/api/route/from/'+str(args[0])+'/to/'+str(args[1]))
            if (not cached):
                r = requests.get('http://api.eve-central.com/api/route/from/'+str(args[0])+'/to/'+str(args[1]), timeout=4)
                if (r.status_code != 200):
                    return 'The API returned error code <b>' + str(r.status_code) + '</b>. System names are case-sensitive. Make sure both systems exist and are reachable from known space.'
                all_waypoints = r.json()
                self.setCache('http://api.eve-central.com/api/route/from/'+str(args[0])+'/to/'+str(args[1]), doc=str(r.text), expiry=int(time.time()+24*60*60))
            else:
                all_waypoints = json.loads(cached)
            if (all_waypoints == []):
                return 'Can\'t calculate a route.'
            jumps = 0
            reply = 'Calculated a route from ' + str(args[0]) + ' to ' + str(args[1]) + '.'
            for waypoint in all_waypoints:
                jumps += 1
                reply += '<br />' + str(waypoint['from']['name']) + '(' + str(waypoint['from']['security']) + '/<i>' + str(waypoint['from']['region']['name']) + '</i>) -> ' + str(waypoint['to']['name']) + '(' + str(waypoint['to']['security']) + '/<i>' + str(waypoint['to']['region']['name']) + '</i>)'
            reply += '<br /><b>' + str(jumps) + '</b> jumps total'
        except requests.exceptions.RequestException as e:
            return 'There is a problem with the API server. Can\'t connect to the server.'

        return reply

    @botcmd
    def evetime(self, mess, args):
        '''[+offset] - Displays the current evetime, server status and the resulting evetime of the offset, if provided'''
        timefmt = '%Y-%m-%d %H:%M:%S'
        evetime = datetime.utcnow()
        reply = 'The current EVE time is ' + evetime.strftime(timefmt)
        try:
            offset_time = timedelta(hours=int(args)) + evetime
            reply += ' and {} hour(s) is {}'.format(args.strip(), offset_time.strftime(timefmt))
        except ValueError:
            pass
        try:
            cached = self.getCache('https://api.eveonline.com/server/serverstatus.xml.aspx')
            if (not cached):
                r = requests.get('https://api.eveonline.com/server/serverstatus.xml.aspx', headers={ 'User-Agent' : 'VM JabberBot'}, timeout=3)
                if (r.status_code != 200 or r.encoding != 'utf-8'):
                    return 'The ServerStatus-API returned error code <b>' + str(r.status_code) + '</b> or the XML encoding is broken.'
                xml = ET.fromstring(r.text)
                self.setCache('https://api.eveonline.com/server/serverstatus.xml.aspx', doc=str(r.text), expiry=int(calendar.timegm(time.strptime(xml[2].text, '%Y-%m-%d %H:%M:%S'))))
            else:
                xml = ET.fromstring(cached)
            if (xml[1][0].text == 'True'):
                reply += '\nThe server is online and ' + str(xml[1][1].text) + ' players are playing'
            else:
                reply += '\nThe server is offline'
        except requests.exceptions.RequestException as e:
            reply += '\nThere is a problem with the API server. Can\'t access ServerStatus-API.'
        return reply

    @botcmd
    def zbot(self,mess,args):
        '''<zKB link> - Displays statistics of a killmail'''
        try:
            # Resolves typeIDs to their names
            def getTypeName(pID):
                try:
                    cached = self.getCache('https://api.eveonline.com/eve/TypeName.xml.aspx', params={'ids' : pID})
                    if (not cached):
                        r = requests.post('https://api.eveonline.com/eve/TypeName.xml.aspx', data={'ids' : pID}, headers={ 'User-Agent' : 'VM JabberBot'}, timeout=3)
                        xml = ET.fromstring(r.text)
                        self.setCache('https://api.eveonline.com/eve/TypeName.xml.aspx', doc=str(r.text), expiry=int(calendar.timegm(time.strptime(xml[2].text, '%Y-%m-%d %H:%M:%S'))), params={'ids' : pID})
                    else:
                        xml = ET.fromstring(cached)
                    apireply = str(xml[1][0][0].attrib['typeName'])
                except:
                    apireply = str('[API Error]')
                finally:
                    return apireply
            # Resolves IDs to their names; can be used to resolve characterID, agentID, corporationID, allianceID, factionID
            def getName(pID):
                    try:
                        cached = self.getCache('https://api.eveonline.com/eve/charactername.xml.aspx', params={'ids' : pID})
                        if (not cached):
                            r = requests.post('https://api.eveonline.com/eve/charactername.xml.aspx', data={'ids' : pID}, headers={ 'User-Agent' : 'VM JabberBot'}, timeout=3)
                            xml = ET.fromstring(r.text)
                            self.setCache('https://api.eveonline.com/eve/charactername.xml.aspx', doc=str(r.text), expiry=int(calendar.timegm(time.strptime(xml[2].text, '%Y-%m-%d %H:%M:%S'))), params={'ids' : pID})
                        else:
                            xml = ET.fromstring(cached)
                        apireply = str(xml[1][0][0].attrib['name'])
                    except:
                        apireply = str('[API Error]')
                    finally:
                        return apireply

            args = args.strip()
            regex = re.match('https:\/\/zkillboard\.com\/kill\/(\d+)\/?', args)
            if (regex == None):
                return 'Please provide a link to a zKB Killmail'
            args = regex.group(1)
            cached = self.getCache('https://zkillboard.com/api/killID/' + str(args) + '/')
            if (not cached):
                r = requests.get('https://zkillboard.com/api/killID/' + str(args) + '/', headers={'Accept-Encoding' : 'gzip', 'User-Agent' : 'VM JabberBot'}, timeout=6)
                if (r.status_code != 200 or r.encoding != 'utf-8'):
                    return 'The zKB-API returned error code <b>' + str(r.status_code) + '</b> or the encoding is broken.'
                killdata = r.json()
                self.setCache('https://zkillboard.com/api/killID/' + str(args) + '/', doc=str(r.text), expiry=int(time.time()+60*60))
            else:
                killdata = json.loads(cached)
            reply = '<b>' + (str(killdata[0]['victim']['characterName']) if str(killdata[0]['victim']['characterName']) != '' else (str(killdata[0]['victim']['corporationName']) + '\'s POS')) + '</b> got killed while flying a/an <b>' + str(getTypeName(killdata[0]['victim']['shipTypeID'])) + '</b> in <b>' + str(getName(killdata[0]['solarSystemID'])) + '</b> at ' + str(killdata[0]['killTime']) + '<br />'
            if (str(killdata[0]['victim']['characterName']) != ''):
                reply += str(killdata[0]['victim']['characterName']) + ' is in corporation ' + str(killdata[0]['victim']['corporationName']) + ((' in alliance ' + str(killdata[0]['victim']['allianceName'])) if str(killdata[0]['victim']['allianceName']) != '' else '') + ((' in faction ' + str(killdata[0]['victim']['factionName'])) if str(killdata[0]['victim']['factionName']) != '' else '') + ' and took <b>{:,}</b> damage'.format(int(killdata[0]['victim']['damageTaken'])) + '<br />'
            else:
                reply += 'The POS is from corporation ' + str(killdata[0]['victim']['corporationName']) + ((' in alliance ' + str(killdata[0]['victim']['allianceName'])) if str(killdata[0]['victim']['allianceName']) != '' else '') + ((' in faction ' + str(killdata[0]['victim']['factionName'])) if str(killdata[0]['victim']['factionName']) != '' else '') + ' and took <b>{:,}</b> damage'.format(int(killdata[0]['victim']['damageTaken'])) + '<br />'
            reply += 'The total value of the ship was <b>{:,.2f}</b> ISK for <b>{:,}</b> point(s) (<i>{}</i>)<br />'.format(float(killdata[0]['zkb']['totalValue']), int(killdata[0]['zkb']['points']), str(killdata[0]['zkb']['source']))
            attackerShips = []
            for char in killdata[0]['attackers']:
                attackerShips.append(char['shipTypeID'])
            cached = self.getCache('https://api.eveonline.com/eve/TypeName.xml.aspx', params={'ids' : ','.join(map(str, attackerShips))})
            if (not cached):
                r = requests.post('https://api.eveonline.com/eve/TypeName.xml.aspx', data={'ids' : ','.join(map(str, attackerShips))}, headers={ 'User-Agent' : 'VM JabberBot'}, timeout=3)
                if (r.status_code != 200 or r.encoding != 'utf-8'):
                    return 'The TypeName-API returned error code <b>' + str(r.status_code) + '</b> or the XML encoding is broken.'
                xml = ET.fromstring(r.text)
                self.setCache('https://api.eveonline.com/eve/TypeName.xml.aspx', doc=str(r.text), expiry=int(calendar.timegm(time.strptime(xml[2].text, '%Y-%m-%d %H:%M:%S'))), params={'ids' : ','.join(map(str, attackerShips))})
            else:
                xml = ET.fromstring(cached)
            attackerShips = []
            for row in xml[1][0]:
                attackerShips.append(row.attrib['typeName'])
            attackerCount = 1
            for char in killdata[0]['attackers']:
                if (attackerCount <= 5):
                    if (str(char['characterName']) != ''):
                        reply += '<b>{}</b> did {:,} damage flying a {} (<i>{:,.2%} of total damage</i>)'.format(str(char['characterName']), int(char['damageDone']), str(attackerShips[attackerCount-1]), float(char['damageDone'])/int(killdata[0]['victim']['damageTaken'])) + (' and scored the <b>final blow</b>' if int(char['finalBlow']) == 1 else '') + '<br />'
                    else:
                        reply += '<b>{}\'s POS</b> did {:,} damage (<i>{:,.2%} of total damage</i>)'.format(str(char['corporationName']), int(char['damageDone']), float(char['damageDone'])/int(killdata[0]['victim']['damageTaken'])) + (' and scored the <b>final blow</b>' if int(char['finalBlow']) == 1 else '') + '<br />'
                elif (int(char['finalBlow'] == 1)):
                    if (str(char['characterName']) != ''):
                        reply += '<b>{}</b> did {:,} damage flying a {} (<i>{:,.2%} of total damage</i>) and scored the <b>final blow</b><br />'.format(str(char['characterName']), int(char['damageDone']), str(attackerShips[attackerCount-1]), float(char['damageDone'])/int(killdata[0]['victim']['damageTaken']))
                    else:
                        reply += '<b>{}\'s POS</b> did {:,} damage (<i>{:,.2%} of total damage</i>) and scored the <b>final blow</b><br />'.format(str(char['corporationName']), int(char['damageDone']), float(char['damageDone'])/int(killdata[0]['victim']['damageTaken']))
                attackerCount += 1
            reply = reply[:-6]
        except requests.exceptions.RequestException as e:
            return 'There is a problem with the API server. Can\'t connect to the server.'
        return reply

    @botcmd(hidden=True)
    # Very rough hack, needs validation and shit
    def goosolve(self, mess, args):
        '''goosolve - Calculates R16 price points. Params: <r64 price> <r32 price> <alch profit/mo>, defaults are 60k, 25k, 400m.'''
        if len(args) == 0:
            r64 = '60000';
            r32 = '25000';
            maxAlch = '400000000';
        else:
            (r64, r32, maxAlch) = args.split(" ")[:3]

        recipes = []
        recipe = []
        recipe += ["Fluxed Condensates"]
        recipe += [parse_expr("("+r64+"*100*2)/200*1.15")]
        recipe += ["100 <b>plat</b> + 5 van"]
        recipe += [parse_expr("solve(Eq((40*"+str(recipe[1])+"-(14000*5+x*100.))*24*30, "+maxAlch+".), x)")]
        recipes += [recipe]
        recipe = []

        recipe += ["Neo Mercurite"]
        recipe += [parse_expr("("+r32+"*100+"+r64+"*100)/200*1.15")]
        recipe += ["100 <b>plat</b> + 5 merc"]
        recipe += [parse_expr("solve(Eq((40*"+str(recipe[1])+"-("+r32+"*5+x*100.))*24*30, "+maxAlch+".), x)")]
        recipes += [recipe]
        recipe = []

        recipe += ["Thulium Hafnite"]
        recipe += [parse_expr("("+r32+"*100+"+r64+"*100)/200*1.15")]
        recipe += ["100 <b>van</b> + 5 haf"]
        recipe += [parse_expr("solve(Eq((40*"+str(recipe[1])+"-("+r32+"*5+x*100.))*24*30, "+maxAlch+".), x)")]
        recipes += [recipe]
        recipe = []

        recipe += ["Dysporite"]
        recipe += [parse_expr("("+r32+"*100+"+r64+"*100)/200*1.15")]
        recipe += ["100 <b>cad</b> + 5 merc"]
        recipe += [parse_expr("solve(Eq((40*"+str(recipe[1])+"-("+r32+"*5+x*100.))*24*30, "+maxAlch+".), x)")]
        recipes += [recipe]
        recipe = []

        recipe += ["Ferrofluid"]
        recipe += [parse_expr("("+r32+"*100+"+r64+"*100)/200*1.15")]
        recipe += ["100 <b>cad</b> + 5 haf"]
        recipe += [parse_expr("solve(Eq((40*"+str(recipe[1])+"-("+r32+"*5+x*100.))*24*30, "+maxAlch+".), x)")]
        recipes += [recipe]
        recipe = []

        recipe += ["Hyperflurite"]
        recipe += [parse_expr("(14000*100+"+r64+"*100)/200*1.15")]
        recipe += ["100 <b>chrom</b> + 5 van"]
        recipe += [parse_expr("solve(Eq((40*"+str(recipe[1])+"-(14000*5+x*100.))*24*30, "+maxAlch+".), x)")]
        recipes += [recipe]
        recipe = []

        recipe += ["Prometium"]
        recipe += [parse_expr("(14000*100+"+r64+"*100)/200*1.15")]
        recipe += ["100 <b>chrom</b> + 5 cad"]
        recipe += [parse_expr("solve(Eq((40*"+str(recipe[1])+"-(14000*5+x*100.))*24*30, "+maxAlch+".), x)")]
        recipes += [recipe]
        recipe = []

        reply = "Calculating R16 price points, with R64s = {:,}, R32s = {:,}, max. monthly alchemy profit = {:,}.<br />".format(int(r64),int(r32),int(maxAlch))
        reply += "<span style=\"font-family:Courier\">{:32}{:23}{:30}{:20}".format("<b>Normal reaction</b>", "<b>Price Target</b>", "<b>Alchemy Reaction</b>", "<b>R16 price target</b><br />")

        for i in range(len(recipes)):
            reply += "{:25}{:<16,d}{:<30}{:<20,d}<br />".format(recipes[i][0], int(recipes[i][1]), recipes[i][2], int(str(recipes[i][3])[1:-12]))
        return reply+"</span>"


    @botcmd
    def rcbl(self, mess, args):
        '''<name>[, ...] - Asks the RC API if <pilot name> has an entry in the blacklist.'''
        # Remove verify=False as soon as python 2.7.7 hits (exp. May 31, 2014).
        # Needed due to self-signed cert with multiple domains + requests/urllib3
        # Ref.:
        #     https://github.com/kennethreitz/requests/issues/1977
        #     http://legacy.python.org/dev/peps/pep-0466/
        #     http://legacy.python.org/dev/peps/pep-0373/
        result = []
        for pilot in [a.strip() for a in args.split(',')]:
            response = requests.get(''.join([vmc.blurl, vmc.blkey, '/', pilot]), verify=False)
            result.append('{} is {}'.format(pilot, response.json()[0]['output']))

        if len(result) > 1:
            result.insert(0, '')
        return '<br />'.join(result)

    def getCache(self, path, params=dict()):
        try:
            if (type(params) != type(dict()) or type(path) != type(str())):
                return None

            conn = sqlite3.connect("api.cache")
            cur = conn.cursor()

            if (len(params) == 0):
                cur.execute("SELECT response FROM cache WHERE path=:path AND expiry>:expiry;", {"path":path,"expiry":time.time()})
                res = cur.fetchall()
                cur.close()
                conn.close()
                if (len(res) == 0 or len(res) > 1):
                    return None
                return res[0][0]

            paramlist = ""
            for val in params.values():
                paramlist += val + "+"
            params = paramlist[:-1]
            cur.execute("SELECT response FROM cache WHERE path=:path AND params=:params AND expiry>:expiry;", {"path":path, "params":params, "expiry":int(time.time())})
            res = cur.fetchall()
            cur.close()
            conn.close()
            if (len(res) == 0 or len(res) > 1):
                return None
            return res[0][0]
        except:
            return None

    def setCache(self, path, doc, expiry, params=dict()):
        try:
            if (type(params) != type(dict()) or type(path) != type(str()) or type(doc) != type(str()) or type(expiry) != type(int())):
                return False
            conn = sqlite3.connect("api.cache")
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS metadata (type VARCHAR(255) NOT NULL UNIQUE, value INT NOT NULL);")

            cur.execute("SELECT value FROM metadata WHERE type='version';")
            res = cur.fetchall()
            if (len(res) == 1 and res[0][0] != self.cache_version):
                cur.execute("DROP TABLE cache;")
            conn.commit()

            cur.execute("INSERT OR REPLACE INTO metadata VALUES (:type, :version);", {"type":"version","version":self.cache_version})
            cur.execute("CREATE TABLE IF NOT EXISTS cache (path VARCHAR(255) NOT NULL, params VARCHAR(255), response TEXT NOT NULL, expiry INT);")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS Query ON cache (path, params);")
            cur.execute("DELETE FROM cache WHERE expiry<=:expiry;", {"expiry":int(time.time())})

            if (len(params) == 0):
                cur.execute("INSERT INTO cache VALUES (:path, :params, :response, :expiry);", {"path":path, "params":"", "response":doc, "expiry":expiry})
                conn.commit()
                cur.close()
                conn.close()
                return True

            # Fix for params (dict) in table
            paramlist = ""
            for val in params.values():
                paramlist += val + "+"
            params = paramlist[:-1]
            cur.execute("INSERT INTO cache VALUES (:path, :params, :response, :expiry);", {"path":path, "params":params, "response":doc, "expiry":expiry})
            conn.commit()
            cur.close()
            conn.close()
            return True
        except:
            return False

    def getAccessToken(self):
        r = requests.post('https://login.eveonline.com/oauth/token', data={'grant_type' : 'refresh_token', 'refresh_token' : vmc.refresh_token}, headers={'Authorization' : 'Basic '+base64.b64encode(vmc.client_id+':'+vmc.client_secret), 'User-Agent' : 'VM JabberBot'})
        res = r.json()
        self.access_token = res['access_token']
        self.token_expiry = time.time()+res['expires_in']

