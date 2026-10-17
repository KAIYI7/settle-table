# Receipt dining splitter

Language for dividing a dining receipt and recording who paid and who reimbursed whom. These definitions do not choose storage, synchronization or business policies.

## Language

**Meal**:
The dining occasion whose receipt, participants and shared costs are being recorded.
_Avoid_: Group (when referring to one dining occasion)

**Participant**:
A person included in a meal's cost allocation, payments or settlements.
_Avoid_: User (when no application account is implied)

**Receipt item**:
A line on the receipt describing a purchased food, drink or other sale item and its stated quantity and amount.
_Avoid_: Expense (when referring to one receipt line)

**Item allocation**:
The portion of a receipt item's cost assigned to a participant.
_Avoid_: Payment (when referring to a share of consumption)

**Receipt total**:
The final amount charged for the meal, including the receipt's applicable charges, discounts and rounding.
_Avoid_: Subtotal

**Subtotal**:
The receipt's intermediate total before the additional adjustments identified on that receipt. Its stated basis may include or exclude tax; the printed label alone does not establish that basis.
_Avoid_: Receipt total

**Consumption**:
The meal cost attributed to a participant through their item allocations and applicable adjustments.
_Avoid_: Paid amount

**Canonical item subtotal**:
The sum of reviewed receipt-item amounts on the selected tax and discount basis. It can differ from another printed subtotal that uses a different basis.
_Avoid_: Printed subtotal (without specifying its basis)

**Included tax**:
Tax already contained in the stated item or meal amount, shown separately as information on the receipt.
_Avoid_: Added charge (when the tax is already included)

**Payer contribution**:
An amount a participant paid toward the restaurant's charge for the meal.
_Avoid_: Settlement (for payment to the restaurant)

**Settlement**:
A transfer between participants to reimburse meal costs.
_Avoid_: Consumption, restaurant payment
