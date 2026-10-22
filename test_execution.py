import json,tempfile,unittest,urllib.error,socket
from pathlib import Path
from unittest.mock import Mock,patch
import execution
class Transactions(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.j=patch.object(execution,'JOURNAL',Path(self.temp.name)/'journal.json');self.j.start();self.sleep=patch('execution.time.sleep');self.sleep.start()
  self.payload={'isAgress':'0','enquiryId':'test','applyType':'12','creEnquiryApprovalAutting12':'test-token'}
 def tearDown(self):self.sleep.stop();self.j.stop();self.temp.cleanup()
 def client(self,answers):
  c=Mock();responses=iter(answers)
  c.request.side_effect=lambda path,body=None:('https://j.esgcc.com.cn'+path,json.dumps(next(responses)))
  return c
 def test_save_success_is_pending_reconciliation(self):
  c=self.client([{'resultCode':'00'},True,{'resultCode':'00','resultMessage':'审批通过'}]);ok,_=execution.submit(c,'key',self.payload)
  self.assertTrue(ok);self.assertEqual(execution.load()['key']['state'],'save_confirmed');self.assertEqual(c.request.call_count,3)
  execution.reconciled(['key']);self.assertEqual(execution.load()['key']['state'],'reconciled')
 def test_uncertain_save_never_retried(self):
  c=self.client([{'resultCode':'00'},True,{'resultCode':'99'}]);self.assertFalse(execution.submit(c,'key',self.payload)[0]);self.assertFalse(execution.submit(c,'key',self.payload)[0]);self.assertEqual(c.request.call_count,3)
 def test_cancelled_workflow_cannot_save(self):
  c=self.client([{'resultCode':'00'},False]);self.assertFalse(execution.submit(c,'key',self.payload)[0]);self.assertEqual(c.request.call_count,2)
 def test_unknown_token_response_cannot_save(self):
  c=self.client([{}]);self.assertFalse(execution.submit(c,'key',self.payload)[0]);self.assertEqual(c.request.call_count,1)
 def test_timeout_reservation_blocks_future_retries(self):
  c=Mock();c.request.side_effect=TimeoutError();self.assertFalse(execution.submit(c,'key',self.payload)[0]);self.assertFalse(execution.submit(c,'key',self.payload)[0]);self.assertEqual(c.request.call_count,1)
 def test_connection_refused_before_save_can_retry(self):
  c=Mock();answers=iter([{'resultCode':'00'},True,urllib.error.URLError(ConnectionRefusedError()),{'resultCode':'00','resultMessage':'审批通过'}])
  def request(path,body=None):
   v=next(answers)
   if isinstance(v,Exception):raise v
   return 'https://j.esgcc.com.cn'+path,json.dumps(v)
  c.request.side_effect=request
  self.assertTrue(execution.submit(c,'key',self.payload)[0]);self.assertEqual(c.request.call_count,4)
 def test_response_timeout_is_never_retried(self):
  c=Mock();c.request.side_effect=urllib.error.URLError(TimeoutError())
  self.assertFalse(execution.submit(c,'key',self.payload)[0]);self.assertEqual(c.request.call_count,1)
if __name__=='__main__':unittest.main()
