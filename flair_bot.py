"""Flair bot, extended to use the Mixer REST API to verify if a requesting user is a partner on mixer."""
import sys, os, re, codecs, csv

from time import gmtime, strftime
import praw

# Required for Mixer API
import requests

try:
    from configparser import ConfigParser
except ImportError:
    # noinspection PyUnresolvedReferences
    from ConfigParser import ConfigParser


class PartnerFlairBot:
    """Flair bot."""

    def __init__(self):
        """Initial setup."""
        self.msgs_read = 0
        try:
            for arg in sys.argv:
                if arg == '-q' or arg == '--quiet':
                    self.debug = False
                else:
                    self.debug = True
        except IndexError:  # Error will be raised if no args are passed in
            self.debug = True

        self.conf = ConfigParser()
        self.flairs = {}
        self.reddit = None
        self.msgtypo = False

        os.chdir(sys.path[0])
        if os.path.exists('conf.ini'):
            self.conf.read('conf.ini')
        else:
            raise FileNotFoundError('Config file, conf.ini, was not found.')

        if self.conf.get('log', 'logging') == 'False':
            self.logging = False
        else:
            self.logging = True

        self.login()

    def login(self):
        """Log in via script/web app."""

        app_id = self.conf.get('app', 'app_id')
        app_secret = self.conf.get('app', 'app_secret')
        user_agent = self.conf.get('app', 'user_agent')

        if self.conf.get('app', 'auth_type') == 'webapp':
            token = self.conf.get('auth-webapp', 'token')
            self.reddit = praw.Reddit(client_id=app_id,
                                      client_secret=app_secret,
                                      refresh_token=token,
                                      user_agent=user_agent)
        else:
            username = self.conf.get('auth-script', 'username')
            password = self.conf.get('auth-script', 'passwd')
            self.reddit = praw.Reddit(client_id=app_id,
                                      client_secret=app_secret,
                                      username=username,
                                      password=password,
                                      user_agent=user_agent)

            if self.debug:
                print('Checking if Login succeeded:')
                if self.reddit.user.me() == username:
                    print('Success! Logged in as %s' % self.reddit.user.me())
                else:
                    print('Login failed. Is the script authorized?')
                    sys.exit(1)

        self.get_flairs()

    def get_flairs(self):
        """Read flairs from CSV."""

        with open('flair_list.csv') as csvf:
            if self.debug:
                print('Opening Flair Styles...')
            csvf = csv.reader(csvf)
            flairs = {}
            for row in csvf:
                if len(row) == 2:
                    flairs[row[0]] = row[1]
                else:
                    flairs[row[0]] = None

        self.flairs = flairs
        self.fetch_pms()

    def fetch_pms(self):
        """Grab unread PMs."""
        if self.debug:
            print("Fetching unread PMs...")

        target_sub = self.conf.get('subreddit', 'name')
        valid = r'[A-Za-z0-9_-]+'
        subject = self.conf.get('subject', 'subject')
        for msg in self.reddit.inbox.unread():
            author = str(msg.author)
            valid_user = re.match(valid, author)
            if msg.subject == subject and valid_user:
                self.process_pm(msg, author, target_sub)

        if self.debug:
            if self.msgs_read == 1:
                print('1 Flair Updated.')
            elif self.msgs_read > 1:
                print('%i Flairs Updated.' % self.msgs_read)
            else:
                print('No new messages. Exiting...')
        sys.exit()

    def process_pm(self, msg, author, target_sub):
        """Process unread PM."""

        content = msg.body.split(',', 1)
        class_name_short = content[0].rstrip()
        try:
            class_name = self.flairs[class_name_short]
        except KeyError:
            if self.debug:
                print('ERROR: Bad Flair Style: %s! Falling back to default flair style.' % class_name_short)
            self.msgtypo = True
            class_name = class_name_short = 'default'

        if self.debug:
            print('selected flair style: %s' % class_name)

        subreddit = self.reddit.subreddit(target_sub)

        """Typos and Missing Info Fixes!
        I've added these as they come up. The system is now pretty resilient to most common mistypes and mistakes."""

        # Good case; a message was sent with everything it should have.
        if len(content) > 1:
            mixer_name = content[1].lstrip()[:64]

        # On the other hand, if they *only* put in a username, then we've assumed the default flair style.
        elif self.msgtypo:
            mixer_name = content[0].lstrip()[:64]

        # If user just supplied flair style without username, then we're assuming their reddit username *is* the
        # mixer name.
        else:
            mixer_name = author

        # Added code to automatically remove [ ] from inputted names since enough people keep doing it!
        if mixer_name[0] == "[":
            mixer_name = mixer_name[1:]
        if mixer_name[-1] == "]":
            mixer_name = mixer_name[:-1]

        flair_text = 'mixer.com/' + mixer_name

        if self.partner_verified(mixer_name):
            subreddit.flair.set(author, flair_text, class_name)
            self.reddit.redditor(author).message('Mixer Partner Flair Request Applied', 'Your request for partner '
                                                                                        'flair has been approved and '
                                                                                        'applied with the **%s** '
                                                                                        'style. If you want to change '
                                                                                        'the style of your flair, '
                                                                                        'please send another message '
                                                                                        'to our bot /u/mixermind.'
                                                 % class_name_short)
        else:
            self.reddit.redditor(author).message('Mixer Partner Flair Request Denied', 'Your request for partner '
                                                                                       'flair has been **denied**, '
                                                                                       'because we could not confirm '
                                                                                       'that [%s](https://%s) is a '
                                                                                       'channel with partner status. '
                                                                                       'If you made a typo, '
                                                                                       'please re-send the corrected '
                                                                                       'message to our bot, '
                                                                                       '/u/mixermind.'
                                                 % (mixer_name, flair_text))
            if self.debug:
                print('%s is not a partner! No flair applied.' % author)

        if self.logging:
            self.log(author, flair_text, class_name, self.partner_verified(mixer_name))

        self.msgs_read += 1
        msg.mark_read()

    def partner_verified(self, mixer_name):
        """Checks with Mixer.com to see if the supplied user is a partner."""
        # Mixer API - Partnered REST Response
        s = requests.session()
        channel_response = s.get('https://mixer.com/api/v1/channels/{}'.format(mixer_name))

        try:
            is_partner = channel_response.json()['partnered']
        except KeyError:
            return False

        if is_partner:
            return True
        else:
            return False

    def log(self, user, text, cls, approved):
        """Log applied flairs to file."""

        with codecs.open('log.txt', 'a', 'utf-8') as logfile:
            time_now = strftime("%Y-%m-%d %H:%M:%S", gmtime())
            log = 'user: ' + user
            if approved:
                log += ' | decision: APPROVED'
            else:
                log += ' | decision: DENIED'
            log += ' @ ' + time_now + '\n'
            logfile.write(log)


PartnerFlairBot()
