// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract LandTransaction {
    address public oracleAddress;

   
    event TransactionAdded(
        uint256 indexed transactionId,
        uint256 indexed parcelId,
        uint256 amount
    );


    mapping(uint256 => bool) public verifiedTransactions;

    constructor(address _oracleAddress) {
        oracleAddress = _oracleAddress;
    }

  
    function verifyPayment(uint256 _transactionId, uint256 _amount) external {
       
        require(msg.sender == oracleAddress, "Only oracle can verify payments");
        
       
        verifiedTransactions[_transactionId] = true;
        
        
        emit TransactionAdded(_transactionId, 0, _amount); 
    }

    
    function isPaymentVerified(uint256 _transactionId) external view returns (bool) {
        return verifiedTransactions[_transactionId];
    }
}
