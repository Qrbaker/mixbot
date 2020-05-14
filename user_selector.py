"""Code to automatically scrape the users from top-level comments of a given thread, then select a number of them at
random."""
import sys, getopt, os, re, csv

# For winner selection (cryptographically secure)
import secrets
# Python Reddit Api Wrapper (P.R.A.W)
import praw

# Tkinter lib for GUI
import tkinter as tk
import tkinter.scrolledtext as tkscroll

try:
    from configparser import ConfigParser
except ImportError:
    # noinspection PyUnresolvedReferences
    from ConfigParser import ConfigParser


class CommentSelectorBot:
    """Comment Selection Bot."""

    def __init__(self, url, capture_output=False, capture_field=None, debug=True, remove=True, winners=1):
        """Initializer"""
        self.debug = debug
        self.remove_post = remove
        self.post_url = url
        self.pick_num = winners
        self.console = capture_field

        self.conf = ConfigParser()

        self.reddit = None
        self.submission = None

        if capture_output:
            sys.stdout = TextRedirector(self.console, "stdout")
            sys.stderr = TextRedirector(self.console, "stderr")

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

        self.message_winner_list("doinkmahoojik", self.winners)

        if self.remove_post:
            self.remove_submission(self.submission)

    def get_submission_from_url(self, submission_url):
        return self.reddit.submission(url=thread_url)

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
            redditors.append(comment)
            if self.debug:
                print('Added %s to pool' % comment.author)
        if self.debug:
            print('Finished parsing comments. %i users have been added to selection pool.' % len(redditors))

        return redditors

    def pick_winners_from_list(self, name_list, num_of_winners=1):
        """Given a list of strings, pick `n` winners from list."""
        if num_of_winners > len(name_list):
            if self.debug:
                print('More winners asked for than people entered!\nReturning all entrants...')
            # If we want to select more winners than people entered, just return everyone.
            return name_list

        winners = []
        for i in range(num_of_winners):
            new_winner = secrets.choice(name_list)
            winners.append(new_winner)
            name_list.remove(new_winner)
        if self.debug:
            print('Selected winners this run:')
            for v in winners:
                print("\t%s" % v.author.name)
        return winners

    def message_winner_list(self, recipient, winner_list):
        nice_win_str = ""
        for winner_comment in winner_list:
            nice_win_str += "- [" + winner_comment.author.name + "](" + winner_comment.permalink + ")  \n"
        self.reddit.subreddit(recipient).message('Winner selections!',
                                                 'Here are the winner selections from the thread "[%s](%s)":  \n%s'
                                                 % (self.submission.title, self.post_url, nice_win_str))

    def remove_submission(self, submission):
        if not submission:
            if self.debug:
                print("Error: Called `remove_submission` with null argument.", file=sys.stderr)
        submission.mod.sticky(state=False)
        submission.mod.lock()  # Prevent addtl. comments
        selected_note = submission.reply("We have selected a winner, and will announce them in the next Featured "
                                         "Streamer post. Thanks to everyone who entered!\n\n"
                                         "*This comment was made by an automated bot. If you have questions, please "
                                         "[contact the r/mixer moderation team.]"
                                         "(http://www.reddit.com/message/compose?to=/r/mixer&message={url})*")
        selected_note.mod.distinguish(how='yes', sticky=True)


# Class used to capture console and print it in the GUI
# from https://stackoverflow.com/questions/12351786/how-to-redirect-print-statements-to-tkinter-text-widget
class TextRedirector(object):
    def __init__(self, widget, tag="stdout"):
        self.widget = widget
        self.tag = tag
        self.errtext = False

    def write(self, str):
        self.widget.configure(state="normal")
        self.widget.insert(tk.END, str, (self.tag,))
        self.widget.configure(state="disabled")


root = tk.Tk()
root.title("Selector Bot 3000")
root.resizable(False, False)
root.geometry('400x400')

# TK Variables
rem_var = tk.BooleanVar()


def selector_bot_callback():
    selector = CommentSelectorBot(capture_output=True, capture_field=console_output, url=post_url_entry.get(), remove=rem_var.get(),
                                  winners=int(winner_select.get()))


url_frame = tk.Frame(root)
url_frame.pack()

winner_num_frame = tk.Frame(root)
winner_num_frame.pack(fill=tk.X)

post_url_label = tk.Label(url_frame, text="Post URL")
post_url_entry = tk.Entry(url_frame, relief=tk.GROOVE, width=40)

winner_select_label = tk.Label(winner_num_frame, text="Number of Winners")
winner_select = tk.Spinbox(winner_num_frame, from_=0, to=20, width=5)

C1 = tk.Checkbutton(root, text="Unsticky After Selecting", variable=rem_var)

do_the_thing_button = tk.Button(root, text="Run Selector", command=selector_bot_callback)

console_output = tkscroll.ScrolledText(root, font=("Courier", 8))

# Pack everything
C1.pack()
winner_select_label.pack(side=tk.LEFT)
winner_select.pack(side=tk.RIGHT)
post_url_label.pack(side=tk.LEFT)
post_url_entry.pack(side=tk.RIGHT)
do_the_thing_button.pack()
console_output.pack()
# Widgets go here...
root.mainloop()
root.destroy()