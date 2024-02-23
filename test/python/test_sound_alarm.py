import socketserver
import threading
from Monitoring.Core.Utils.SoundAlarm import send_sound_msg, send_email_msg

MOCK_SOUNDSERVER = "127.0.0.1"
MOCK_PORT = 9999


class MockSoundServer(socketserver.BaseRequestHandler):

    def handle(self):
        # self.request is the TCP socket connected to the client
        self.data = self.request.recv(1024).strip().decode("utf-8", errors="ignore")
        print("Received from {}:".format(self.client_address[0]))
        print(self.data)
        # just send back the same data, but upper-cased
        response = "All ok\n" if "GOOD MSG" in self.data else "laksjdflksajd"
        self.request.sendall(response.encode())


def test_send_sound_msg_success():
    socketserver.TCPServer.allow_reuse_address = True
    socketserver.TCPServer.allow_reuse_port = True
    with socketserver.TCPServer(
        (MOCK_SOUNDSERVER, MOCK_PORT), MockSoundServer
    ) as server:
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        result = send_sound_msg(
            msg="GOOD MSG",
            spoken_msg="GOOD",
            soundserver=MOCK_SOUNDSERVER,
            port=MOCK_PORT,
        )
        server.shutdown()
        server.server_close()
        server_thread.join()
        assert result


def test_send_sound_msg_fail():
    socketserver.TCPServer.allow_reuse_address = True
    socketserver.TCPServer.allow_reuse_port = True
    with socketserver.TCPServer(
        (MOCK_SOUNDSERVER, MOCK_PORT), MockSoundServer
    ) as server:
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        result = send_sound_msg(
            msg="ELA", spoken_msg="E L A", soundserver=MOCK_SOUNDSERVER, port=MOCK_PORT
        )
        server.shutdown()
        server.server_close()
        server_thread.join()
        assert not result


# TODO: Find a way to mock sending an email?
# def test_send_email_success():
#     result = send_email_msg(
#         msg=f"SUCCESSFUL TEST {__name__}",
#         email_addresses="",
#     )
#     assert result


def test_send_email_fail():
    result = send_email_msg(msg="TEST")
    assert not result
