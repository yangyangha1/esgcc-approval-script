import unittest
from unittest.mock import Mock
from runner import command
from client import BASE
class Rules(unittest.TestCase):
 def fixture(self,extra='',args="0,'sample','token',12,0,0,0"):
  return '''<html><body>竞价单审批<table><tr><td>报价方式</td><td>公开报价</td></tr><tr><td>评分规则</td><td>最低价法</td></tr><tr><td>包名称</td><td>测试包</td></tr><tr><td>竞价单总限价</td><td>100</td></tr>'''+extra+'''</table><table><thead><tr><th>单价限价</th></tr></thead><tbody><tr><td>10</td></tr></tbody></table><a onclick="agreeOrDisAgree('''+args+''')">同意</a><script>var route='/creEnquiryWorkflow/save';var tokenName='creEnquiryApprovalAutting12';function beanValidatorForToken(){}function validateEnquiryWorkflow(){}</script></body></html>'''
 def decision(self,html):
  c=Mock();c.request.side_effect=AssertionError('unexpected network call')
  r=command(c,BASE+'/creEnquiryWorkflow/forward/100?applyType=12',html,'detail',{'category':'material','kind':'bid'})
  c.request.assert_not_called();return r
 def test_qualified_bid_is_dry_run_only(self):
  r=self.decision(self.fixture());self.assertTrue(r.get('wouldApprove'));self.assertFalse(r.get('approved'))
 def test_multiround_empty_attachment_is_dry_rejection(self):
  r=self.decision(self.fixture('<tr><td>竞价轮次</td><td>二次竞价</td></tr><tr><td>附件</td><td>无附件</td></tr>'));self.assertTrue(r.get('wouldReject'));self.assertFalse(r.get('approved'))
 def test_multiround_unknown_attachment_is_manual(self):
  r=self.decision(self.fixture('<tr><td>竞价轮次</td><td>二次竞价</td></tr>'));self.assertTrue(r.get('manual'))
 def test_dynamic_onclick_is_not_executed(self):
  r=self.decision(self.fixture(args="0,(function(){throw Error('injection')})(),'token',12,0,0,0"));self.assertFalse(r.get('wouldApprove'));self.assertTrue(r.get('manual'))
 def test_script_and_hidden_cancel_text_do_not_block_confirmation(self):
  html="""<html><body>竞价单审批 确认结果<table><tr><th>报价单总价</th></tr><tr><td>10</td></tr><tr><td>20</td></tr></table><a onclick="agreeOrDisAgree(0,'sample','token',20,0,0,0)">同意</a><script>var label='取消竞价';var token='creEnquiryApprovalAutting20';var route='/creEnquiryWorkflow/save';function beanValidatorForToken(){}function validateEnquiryWorkflow(){}</script><div style="display:none">取消竞价</div></body></html>"""
  c=Mock();c.request.side_effect=AssertionError('unexpected network call')
  r=command(c,BASE+'/creEnquiryWorkflow/forward/100?applyType=20',html,'detail',{'category':'material','kind':'confirm'})
  self.assertTrue(r.get('wouldApprove'));c.request.assert_not_called()
 def test_missing_required_field_blocks(self):
  r=self.decision(self.fixture().replace('公开报价','其他报价'));self.assertTrue(r.get('manual'))
if __name__=='__main__':unittest.main()
