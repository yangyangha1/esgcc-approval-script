import unittest
from unittest.mock import Mock, patch
from client import Client, BASE, SameSiteRedirect
from probe import aes_point

class SessionGates(unittest.TestCase):
    def client(self,url,text):
        c=Client.__new__(Client);c.request=Mock(return_value=(url,text));c.save=Mock();return c
    def test_login_redirect_cannot_be_valid(self):
        c=self.client(BASE+'/login','竞价单审批 退出 <table>');self.assertEqual(c.check(),'LOGIN_REQUIRED');c.save.assert_not_called()
    def test_password_form_cannot_be_valid(self):
        c=self.client(BASE+'/creEnquiryWorkflow/list/1','<input type="password">竞价单审批 退出 <table>');self.assertEqual(c.check(),'LOGIN_REQUIRED')
    def test_empty_or_ambiguous_cannot_be_valid(self):
        for text in ['', '竞价单审批', '<table>退出']:
            c=self.client(BASE+'/creEnquiryWorkflow/list/1',text);self.assertEqual(c.check(),'UNKNOWN');c.save.assert_not_called()
    def test_valid_session_skips_credentials_and_sms(self):
        c=self.client(BASE+'/creEnquiryWorkflow/list/1','竞价单审批 退出 <table></table>')
        with patch('builtins.print'): c.login()
        c.request.assert_called_once();c.save.assert_called_once()
    def test_ambiguous_session_never_sends_sms(self):
        c=self.client(BASE+'/creEnquiryWorkflow/list/1','unexpected page')
        with self.assertRaises(ValueError):c.login()
        c.request.assert_called_once();c.save.assert_not_called()
    def test_redirect_rejects_foreign_host_and_plaintext(self):
        handler=SameSiteRedirect()
        for url in ['https://example.org/login','http://j.esgcc.com.cn/login']:
            with self.assertRaises(ValueError):handler.redirect_request(None,None,302,'',{},url)
    def test_crypto_does_not_expose_key_in_arguments(self):
        with patch('probe.subprocess.run') as p:
            p.return_value.stdout='cipher';self.assertEqual(aes_point('secret',None),'cipher')
            self.assertNotIn('secret',str(p.call_args.args));self.assertIn('"x": null',p.call_args.kwargs['input'])
if __name__=='__main__':unittest.main()
