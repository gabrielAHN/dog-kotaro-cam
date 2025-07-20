import requests
import boto3
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Fetch variables from env (with error checking)
DNS_RECORD = os.getenv('DNS_RECORD')
HOSTED_ZONE_ID = os.getenv('HOSTED_ZONE_ID')

if not DNS_RECORD or not HOSTED_ZONE_ID:
    print('FAILED - Missing DNS_RECORD or HOSTED_ZONE_ID in .env file')
    exit(1)

try:
    client = boto3.client('route53')
except Exception as e:
    print(f'FAILED - Check boto3 installation and AWS credentials in .env: {str(e)}')
    exit(1)

# Get your public IP
def get_public_ip():
    try:
        public_ip = requests.get('https://api.ipify.org').text
        return public_ip
    except Exception as e:
        print(f'FAILED - Could not fetch public IP: {str(e)}')
        return None

# Get the current value of your DNS record from Route 53
def get_record_value():
    try:
        response = client.test_dns_answer(
            HostedZoneId=HOSTED_ZONE_ID,
            RecordName=DNS_RECORD,
            RecordType='A',
        )
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            return response['RecordData'][0]
        else:
            return None
    except Exception as e:
        print(f'FAILED - Check HOSTED_ZONE_ID and DNS_RECORD in AWS: {str(e)}')
        return None

# Change the Route 53 record value
def change_record_value(public_ip):
    try:
        response = client.change_resource_record_sets(
            HostedZoneId=HOSTED_ZONE_ID,
            ChangeBatch={
                'Comment': 'Dynamic DNS Update',
                'Changes': [
                    {
                        'Action': 'UPSERT',
                        'ResourceRecordSet': {
                            'Name': DNS_RECORD,
                            'Type': 'A',
                            'TTL': 300,
                            'ResourceRecords': [
                                {
                                    'Value': public_ip
                                },
                            ],
                        }
                    },
                ]
            }
        )
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            return 'DNS CHANGE SUCCESSFUL'
        else:
            return 'FAILED'
    except Exception as e:
        print(f'FAILED - DNS update error: {str(e)}')
        return 'FAILED'

# Main logic
public_ip = get_public_ip()
if not public_ip:
    exit(1)

record_value = get_record_value()
if record_value is None:
    exit(1)

# Formatting output
padding = len(DNS_RECORD) + 2 - len('Public IP: ')
print('---------------------------')
print(f'Public IP: {padding * " "}{public_ip}')
print(f'{DNS_RECORD}: {record_value}')
print('---------------------------')

if public_ip != record_value:
    print("DNS VALUE DOES NOT MATCH PUBLIC IP")
    result = change_record_value(public_ip)
    print(result)
    if result == 'DNS CHANGE SUCCESSFUL':
        print(f'Check https://console.aws.amazon.com/route53/v2/hostedzones#{HOSTED_ZONE_ID} to verify your DNS change')
else:
    print("NO CHANGE NEEDED")