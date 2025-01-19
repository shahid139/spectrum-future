from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from odoo import SUPERUSER_ID, _, api, Command, fields, models


class StockPickingInherited(models.Model):
    _inherit = 'stock.picking'

    purchase_id = fields.Many2one('purchase.order')


    def button_validate(self):
        draft_picking = self.filtered(lambda p: p.state == 'draft')
        draft_picking.action_confirm()
        for move in draft_picking.move_ids:
            if float_is_zero(move.quantity, precision_rounding=move.product_uom.rounding) and\
               not float_is_zero(move.product_uom_qty, precision_rounding=move.product_uom.rounding):
                move.quantity = move.product_uom_qty

        # Sanity checks.
        if not self.env.context.get('skip_sanity_check', False):
            self._sanity_check()
        self.message_subscribe([self.env.user.partner_id.id])

        # Run the pre-validation wizards. Processing a pre-validation wizard should work on the
        # moves and/or the context and never call `_action_done`.
        if not self.env.context.get('button_validate_picking_ids'):
            self = self.with_context(button_validate_picking_ids=self.ids)
        res = self._pre_action_done_hook()
        if res is not True:
            return res

        # Call `_action_done`.
        pickings_not_to_backorder = self.filtered(lambda p: p.picking_type_id.create_backorder == 'never')
        if self.env.context.get('picking_ids_not_to_backorder'):
            pickings_not_to_backorder |= self.browse(self.env.context['picking_ids_not_to_backorder']).filtered(
                lambda p: p.picking_type_id.create_backorder != 'always'
            )
        pickings_to_backorder = self - pickings_not_to_backorder
        pickings_not_to_backorder.with_context(cancel_backorder=True)._action_done()
        pickings_to_backorder.with_context(cancel_backorder=False)._action_done()
        report_actions = self._get_autoprint_report_actions()
        another_action = False
        if self.user_has_groups('stock.group_reception_report'):
            pickings_show_report = self.filtered(lambda p: p.picking_type_id.auto_show_reception_report)
            lines = pickings_show_report.move_ids.filtered(lambda m: m.product_id.type == 'product' and m.state != 'cancel' and m.quantity and not m.move_dest_ids)
            if lines:
                # don't show reception report if all already assigned/nothing to assign
                wh_location_ids = self.env['stock.location']._search([('id', 'child_of', pickings_show_report.picking_type_id.warehouse_id.view_location_id.ids), ('usage', '!=', 'supplier')])
                if self.env['stock.move'].search([
                        ('state', 'in', ['confirmed', 'partially_available', 'waiting', 'assigned']),
                        ('product_qty', '>', 0),
                        ('location_id', 'in', wh_location_ids),
                        ('move_orig_ids', '=', False),
                        ('picking_id', 'not in', pickings_show_report.ids),
                        ('product_id', 'in', lines.product_id.ids)], limit=1):
                    action = pickings_show_report.action_view_reception_report()
                    action['context'] = {'default_picking_ids': pickings_show_report.ids}
                    if not report_actions:
                        return action
                    another_action = action
        if report_actions:
            return {
                'type': 'ir.actions.client',
                'tag': 'do_multi_print',
                'params': {
                    'reports': report_actions,
                    'anotherAction': another_action,
                }
            }
        return True