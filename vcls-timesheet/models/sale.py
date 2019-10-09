from odoo import models, fields, tools, api
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
import datetime

import logging
_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):

    _inherit = 'sale.order'

    @api.multi
    def action_view_forecast(self):
        self.ensure_one()
        parent_project_id, child_ids = self._get_family_projects()
        action = self.env.ref('project_forecast.project_forecast_action_by_project').read()[0]
        all_project_ids = (parent_project_id | child_ids).ids
        action['context'] = {
            'search_default_future': 1,
            'group_by': ['project_id', 'task_id', 'employee_id'],
        }
        action['domain'] = [('project_id', 'in',  all_project_ids)]
        if len(parent_project_id) == 1 and not child_ids:
            action['context'].update({
                'default_project_id': parent_project_id.id,
            })
        return action

    @api.multi
    def action_view_family_timesheet(self):
        self.ensure_one()
        action = self.env.ref('hr_timesheet.act_hr_timesheet_line').read()[0]
        parent_order_id, child_orders = self._get_family_sales_orders()
        all_orders = parent_order_id | child_orders
        action['domain'] = [('so_line', 'in', all_orders.mapped('order_line').ids)]
        return action

    @api.model
    def create(self, vals):
        result = super(SaleOrder, self).create(vals)
        result.first_quotation()
        return result

    def first_quotation(self):
        if self.opportunity_id:
            if self.opportunity_id.sale_number == 1 : 
                pre_project = self.env.ref('vcls-timesheet.default_project').id
                stage_id = self.env['project.task.type'].sudo().search([('name','=','0% Progress')], limit=1).id
                self.opportunity_id.task_id = self.env['project.task'].sudo().create({
                                                                                    'name':self.opportunity_id.name,
                                                                                    'project_id':pre_project, 
                                                                                    'stage_id':stage_id, 
                                                                                    'active':True}).id
    
    #We override the OCA to inject the stage domain
    
    """@api.depends(
        'timesheet_limit_date',
        'analytic_account_id.line_ids.stage_id',
        'analytic_account_id.line_ids.unit_amount_rounded',
        'analytic_account_id.line_ids.date')"""
    @api.multi
    @api.depends('timesheet_limit_date')
    def _compute_timesheet_ids(self):
        _logger.info("TS PATH | vcls-timesheet | sale.order | _compute_timesheet_ids")
        # this method copy of base method, it injects date in domain
        for order in self:
            if order.analytic_account_id:
                domain = [
                    ('so_line', 'in', order.order_line.ids),
                    ('amount', '<=', 0.0),
                    ('project_id', '!=', False),
                    # OCA override
                    ('stage_id', 'in', ['invoiceable','invoiced']),
                ]
                if order.timesheet_limit_date:
                    domain.append(
                        ('date', '<=', order.timesheet_limit_date)
                    )
                order.timesheet_ids = self.env[
                    'account.analytic.line'].search(domain)
                _logger.info('{} found {}'.format(domain,order.timesheet_ids.mapped('name')))
            else:
                order.timesheet_ids = []
            order.timesheet_count = len(order.timesheet_ids)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _timesheet_compute_delivered_quantity_domain(self):
        domain = super()._timesheet_compute_delivered_quantity_domain()
        #We add the condition on the timesheet stage_id
        domain = expression.AND([
                domain,
                [('stage_id', 'in', ['invoiceable','invoiced'])]]
            )
        #_logger.info("TS PATH | vcls-timesheet | sale.order.line | _timesheet_compute_delivered_quantity_domain | {}".format(domain))

        return domain

    def _get_timesheet_for_amount_calculation(self, only_invoiced=False):
        #_logger.info("TS PATH | vcls-timesheet | sale.order.line | _get_timesheet_for_amount_calculation")

        timesheets = super()._get_timesheet_for_amount_calculation(only_invoiced=only_invoiced)
        
        if not timesheets:
            return timesheets

        #_logger.info('Amount before filter {} | {} | {}'.format(timesheets.mapped('name'),timesheets.mapped('validated'),timesheets.mapped('stage_id')))
        timesheets = timesheets.filtered(
                lambda r: r.stage_id in ['invoiceable', 'invoiced']
            )

        def ts_filter(rec):
            sale = rec.task_id.sale_line_id.order_id
            return (
                sale.state in ('sale', 'done')
                and
                #(sale.timesheet_limit_date or sale.timesheet_limit_date > rec.date)
                (sale.timesheet_limit_date > rec.date if sale.timesheet_limit_date else True)
            )
        timesheets = timesheets.filtered(ts_filter)

        #_logger.info('Amount after filter {} | {} | {}'.format(timesheets.mapped('name'),timesheets.mapped('validated'),timesheets.mapped('stage_id')))
        return timesheets
    
    # We need to override the OCA to take the rounded_unit_amount in account rather than the standard unit_amount
    @api.multi
    @api.depends(
        'task_id',
        'task_id.timesheet_ids.timesheet_invoice_id',
        'task_id.timesheet_ids.unit_amount_rounded',
        'task_id.timesheet_ids.stage_id',
    )
    def _compute_amount_delivered_from_task(self):
        for line in self:
            total = 0
            for ts in line._get_timesheet_for_amount_calculation():

                """rate_line = ts.project_id.sale_line_employee_ids.filtered(
                    lambda r: r.employee_id == ts.employee_id
                )
                total += ts.unit_amount_rounded * rate_line.price_unit"""
                total += ts.unit_amount_rounded * ts.so_line_unit_price
            line.amount_delivered_from_task = total
            line.amount_delivered_from_task_company_currency = (
                total * line.order_id.currency_rate
            )

    @api.multi
    @api.depends('task_id', 'task_id.timesheet_ids.timesheet_invoice_id')
    def _compute_amount_invoiced_from_task(self):
        for line in self:
            total = 0
            for ts in line._get_timesheet_for_amount_calculation(True):
                """rate_line = ts.project_id.sale_line_employee_ids.filtered(
                    lambda r: r.employee_id == ts.employee_id
                )
                total += ts.unit_amount_rounded * rate_line.price_unit"""
                total += ts.unit_amount_rounded * ts.so_line_unit_price
            line.amount_invoiced_from_task = total
            line.amount_invoiced_from_task_company_currency = (
                total * line.order_id.currency_rate
            )


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    name = fields.Char(
        store = True
    )
