from traceback import print_exc
from socket import socket, AF_INET, SOCK_STREAM, gethostname
import smtplib
from email.message import EmailMessage
from subprocess import Popen, PIPE
from Monitoring.Core.Utils.Common import logme

# Body of the XML message that is sent to CMS-WOW
MSGBODY = (
    '<CommandSequence><alarm sender="DQM" sound="DQM_1.wav" talk="{spoken_msg}">'
    "{msg} Check plots in the DQM Error folder.</alarm></CommandSequence>"
)


# Short hand to send XML message to CMS-WOW
def send_sound_msg(
    msg: str, spoken_msg: str, soundserver: str, port: int, email_addresses: str = None
) -> bool:
    with socket(AF_INET, SOCK_STREAM) as s:
        s.connect((soundserver, port))
        s.send(MSGBODY.format(spoken_msg=spoken_msg, msg=msg).encode())
        data = s.recv(1024).decode("utf-8")

    if data == "All ok\n":
        logme(f"INFO: Broadcasted message: {msg}")
        send_email_msg(
            msg="We (DQM) just played a sound in the control room.\n"
            f'The message we played was: "{spoken_msg}"\n\n--\n{msg}',
            email_addresses=email_addresses,
        )
        return True
    else:
        error_msg = f"ERROR: Unexpected answer from CMS-WOW: {repr(data)}"
        logme(error_msg)
        send_email_msg(msg=error_msg, email_addresses=email_addresses)
        return False

    # Short hand to send email message


def send_email_msg(
    msg: str = "", email_addresses: str = None, mail_cmd="/usr/sbin/sendmail -t"
) -> bool:
    if email_addresses:
        process = Popen(mail_cmd, shell=True, stdin=PIPE)
        process.stdin.write(f"To: {email_addresses}\n".encode())
        process.stdin.write(
            f"Subject: Message from the visDQMSoundAlarmDaemon on {gethostname()} at P5\n".encode()
        )
        process.stdin.write("\n".encode())  # blank line separating headers from body
        process.stdin.write(f"{msg}\n\n".encode())
        process.stdin.write(
            f"The logs should be here: /data/srv/logs/dqmgui/online/\n".encode()
        )
        process.stdin.close()
        returncode = process.wait()
        if returncode != 0:
            logme(
                f"ERROR: Sendmail exit with status {returncode}",
            )
            return False
        return True
    else:
        logme("Not sending email, since no emailaddresses were set.")
        return False


# Short hand to extract GUI information, it fails if the retrieved
# data is not python format.
# Looks unused
def getGuiData(opener, url):
    page1 = opener.open(url)
    data = page1.read()
    try:
        contents = eval(data)
    except Exception as e:
        raise e
    page1.close()
    return contents


# This method is just to test the sound infrastructure.
# It will try to play a test message, send a test email and then exit.
def run_test(soundserver, port, email_addresses):
    logme("Running in test mode.")
    msg = "This is a test"
    spoken_msg = "This is a test"
    # First try to test sending a sound message
    logme("Trying to send a sound message.")
    try:
        send_sound_msg(
            msg=msg,
            spoken_msg=spoken_msg,
            soundserver=soundserver,
            port=port,
            email_addresses=email_addresses,
        )
    except Exception as e:
        logme(f"ERROR: {e}")
        print_exc()
    # Then try to test sending an email message
    logme("Trying to send an email message.")
    try:
        send_email_msg(msg=msg, email_addresses=email_addresses)
    except Exception as e:
        logme(f"ERROR: {e}")
        print_exc()
