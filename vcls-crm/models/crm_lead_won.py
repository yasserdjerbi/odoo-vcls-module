# -*- coding: utf-8 -*-

from odoo import api, fields, models

# Basic copy of crm.lost.reason
class WonReason(models.Model):
    _name = "crm.won.reason"
    _description = 'Opp. Won Reason'

    name = fields.Char('Name', required=True)
    active = fields.Boolean('Active', default=True)


# Basic copy of crm.lead.lost
class CrmLeadWon(models.TransientModel):
    _name = 'crm.lead.won'
    _description = 'Get Won Reason'

    won_reason_ids = fields.Many2many('crm.won.reason', string = 'Won Reasons')
    description = fields.Char(string = 'Description')

    @api.multi
    def action_won_reason_apply(self):
        leads = self.env['crm.lead'].browse(self.env.context.get('active_ids'))
        leads.write({'won_reasons': [(6, 0, self.won_reason_ids.ids)], 'won_lost_description': self.description})
        result = leads.action_set_won()
        if result:
            return {
                    'effect': {
                        'fadeout': 'slow',
                        'message': 'Congrats !',
                        'img_url': '/web/static/src/img/smile.svg',
                        'type': 'rainbow_man',
                    }
                }

class CrmLeadLost(models.TransientModel):
    _inherit = 'crm.lead.lost'
    lost_reason_ids = fields.Many2many('crm.lost.reason', string = 'Lost Reasons')
    description = fields.Char(string = 'Description')

    @api.multi
    def action_lost_reason_apply(self):
        leads = self.env['crm.lead'].browse(self.env.context.get('active_ids'))
        leads.write({'lost_reasons': [(6, 0, self.lost_reason_ids.ids)], 'won_lost_description': self.description})
        return leads.action_set_lost()