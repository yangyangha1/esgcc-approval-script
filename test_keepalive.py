import unittest,urllib.error
from unittest.mock import patch
import service
class Keepalive(unittest.TestCase):
 def test_transient_timeout_recovers(self):
  with patch('service.Client') as c,patch('service.time.sleep'):
   c.return_value.check.side_effect=[TimeoutError(), 'LOGIN_OK']
   status,attempts=service.session_probe()
  self.assertEqual(status,'LOGIN_OK');self.assertEqual(len(attempts),2)
 def test_three_failures_are_bounded_and_redacted(self):
  with patch('service.Client') as c,patch('service.time.sleep'):
   c.return_value.check.side_effect=urllib.error.URLError('secret endpoint')
   status,attempts=service.session_probe()
  self.assertEqual(status,'ERROR');self.assertEqual(len(attempts),3);self.assertNotIn('secret',str(attempts))
 def test_explicit_logout_is_not_retried(self):
  with patch('service.Client') as c,patch('service.time.sleep') as sleep:
   c.return_value.check.return_value='LOGIN_REQUIRED';status,a=service.session_probe();sleep.assert_not_called()
  self.assertEqual(status,'LOGIN_REQUIRED');self.assertEqual(len(a),1)
 def test_push_failure_does_not_change_valid_session(self):
  updates=[]
  with patch.dict(service.state,{'session':'ERROR'}),patch('service.session_probe',return_value=('LOGIN_OK',[{'status':'LOGIN_OK'}])),patch('service.update',side_effect=lambda **k:updates.append(k)),patch('service.settings',return_value={}),patch('service.notify',side_effect=ValueError()):service.keepalive()
  self.assertEqual(updates[0]['session'],'LOGIN_OK');self.assertNotIn('session',updates[-1])
if __name__=='__main__':unittest.main()
