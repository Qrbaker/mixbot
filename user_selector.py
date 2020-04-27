"""Code to automatically scrape the users from top-level comments of a given thread, then select a number of them at
random."""
import sys, getopt, os, re, csv

# For winner selection (cryptographically secure)
import secrets
# Python Reddit Api Wrapper (P.R.A.W)
import praw

try:
    from configparser import ConfigParser
except ImportError:
    # noinspection PyUnresolvedReferences
    from ConfigParser import ConfigParser


class CommentSelectorBot:
    """Comment Selection Bot."""

    def __init__(self):
        """Initializer"""
        self.debug = True
        self.post_url = ''
        self.pick_num = 1
        if self.debug:
            print('found %i arguments' % len(sys.argv))
        try:
            for i, arg in enumerate(sys.argv):
                if self.debug:
                    print(arg)
                if arg == '-q' or arg == '--quiet':
                    self.debug = False
                if arg == '-u' or arg == '--url':
                    try:
                        self.post_url = sys.argv[i+1]
                    except IndexError:
                        if self.debug:
                            print("hit end of args.")
                if arg == '-n' or arg == '--number':
                    try:
                        self.pick_num = int(sys.argv[i+1])
                    except ValueError:
                        if self.debug:
                            print("Could not case %s to int." % arg, file=sys.stderr)
                        self.pick_num = 1

        except IndexError:  # Error will be raised if no args are passed in
            print('No args provided! You must include at least one argument, the post url.', file=sys.stderr)
            exit(-1)

        self.conf = ConfigParser()

        self.reddit = None

        os.chdir(sys.path[0])
        if os.path.exists('conf.ini'):
            self.conf.read('conf.ini')
        else:
            raise FileNotFoundError('Config file, conf.ini, was not found.')

        if self.conf.get('log', 'logging') == 'False':
            self.logging = False
        else:
            self.logging = True

        if self.conf.get('winners', 'save_winners') == 'False':
            self.save_winners = False
        else:
            self.save_winners = True

        if self.debug:
            print('Initialization complete!')
        self.login()
        self.get_previous_winners()
        self.user_list = self.get_users_from_thread(self.post_url)
        self.winners = self.pick_winners_from_list(self.user_list, self.pick_num)

        self.message_winner_list("seminal_sound", self.winners)

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

    def get_previous_winners(self):
        """Read previous winners from a csv list."""

        with open('winner_list.csv') as csvf:
            if self.debug:
                print('Opening winner list...')
            csvf = csv.reader(csvf)
            winners = []
            for row in csvf:
                if len(row) > 1:
                    winners.append(row[0][0])
                else:
                    winners.append(row[0])
            if self.debug:
                print("Fetched %i previous winners." % len(winners))
                for winner in winners:
                    print("\t%s" % winner)
            self.prev_winners = winners

    def get_users_from_thread(self, thread_url):
        """Given a thread url, parse all the top-level comment authors."""
        self.submission = self.reddit.submission(url=thread_url)
        top_level_comments = list(self.submission.comments)
        redditors = []
        for comment in top_level_comments:
            if comment.author in redditors:  # Skip already added redditors
                if self.debug:
                    print('Skipping %s, they are already in the list...' % comment.author.name)
                continue
            if comment.author.name in self.prev_winners:  # Skip previous winners
                if self.debug:
                    print("Skipping %s, they have already won previously..." % comment.author.name)
                continue
            redditors.append(comment.author)
            if self.debug:
                print('Added %s to pool' % comment.author)
        if self.debug:
            print('Finished parsing comments. %i users have been added to selection pool.' % len(redditors))

        return redditors

    def pick_winners_from_list(self, name_list, num_of_winners=1):
        """Given a list of strings, pick `n` winners from list."""
        winners = []
        for i in range(num_of_winners):
            new_winner = secrets.choice(name_list)
            winners.append(new_winner)
            name_list.remove(new_winner)
        if self.debug:
            print('Selected winners this run:')
            for v in winners:
                print("\t%s" % v.name)
        return winners

    def message_winner_list(self, recipient, winner_list):
        nice_win_str = ""
        for winner in winner_list:
            nice_win_str += "- " + winner.name + "  \n"
        self.reddit.redditor(recipient).message('Winner selections!',
                                                'Here are the winner selections from the thread "[%s](%s)":  \n%s'
                                                % (self.submission.title, self.post_url, nice_win_str))
CommentSelectorBot()