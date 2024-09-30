import hashlib
import hmac
import base64
import requests
import time
import json
import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime
from ncp_crendential import ncp_credentials, slack_token

slack_token = slack_token()

client = WebClient(token=slack_token)

class NcloudApiClient:
    def __init__(self, access_key, secret_key, api_server):
        self.access_key = access_key
        self.secret_key = bytes(secret_key, 'UTF-8')
        self.api_server = api_server

    def make_signature(self, uri, method="POST"):
        timestamp = str(int(time.time() * 1000))

        message = method + " " + uri + "\n" + timestamp + "\n" + self.access_key
        message = bytes(message, 'UTF-8')

        signingKey = base64.b64encode(hmac.new(self.secret_key, message, digestmod=hashlib.sha256).digest())
        api_endpoint = self.api_server + uri
        http_header = {
            'x-ncp-apigw-signature-v2': signingKey,
            'x-ncp-apigw-timestamp': timestamp,
            'x-ncp-iam-access-key': self.access_key
        }

        return api_endpoint, http_header

    def get_request(self, uri):
        api_endpoint, http_header = self.make_signature(uri, method="GET")

        response = requests.get(api_endpoint, headers=http_header)
        return json.loads(response.text)

    def post_request(self, uri):
        api_endpoint, http_header = self.make_signature(uri, method="POST")
        response = requests.post(api_endpoint, headers=http_header)
        return json.loads(response.text)

def main():
    access_key, secret_key = ncp_credentials()
    billing_api = "https://billingapi.apigw.ntruss.com"

    ncloud_api = NcloudApiClient(access_key, secret_key, billing_api)
    current_month = datetime.now().strftime('%Y%m')
    uri = "/billing/v1/cost/getDemandCostList?startMonth=" + current_month + "&endMonth=" + current_month + "&responseFormatType=json"
    getResponse = ncloud_api.get_request(uri)

    print("Get Response Data:")
    print(getResponse)

    useAmount = getResponse['getDemandCostListResponse']['demandCostList'][0]['useAmount']
    credetDiscount = getResponse['getDemandCostListResponse']['demandCostList'][0]['creditDiscountAmount']
    totalDemandAmount = getResponse['getDemandCostListResponse']['demandCostList'][0]['totalDemandAmount']
    print("총 사용 비용: ")
    print(useAmount)

    channelId = '' # 채널 ID 입력
    Budget = 30000 # 예산 입력
    usePercent = useAmount / Budget * 100
    billingNotification(channelId, usePercent, useAmount, credetDiscount, totalDemandAmount)


def billingNotification(channelId, usePercent, useAmount, creditDiscount, totalDemandAmount):
    # 기본 메시지 템플릿 정의
    baseMessage = (
        '>*[OPEN][{level}] NAVER Cloud Cost Management* \n'
        '>`NAVER Cloud Cost Management Bot`\n'
        '>```\n'
        '[ 계정 ] : 본인 계정 입력\n'
        '[ 계정 타입 ] : 계정 타입 입력 \n'
        '[ 예산 ] : 예산 설정 (30000원) \n'
        '[ 사용 금액 ]: {useAmount}원\n'
        '[ 크레딧 할인 ] : -{creditDiscount}원\n'
        '[ 실제 청구 금액 ] : {totalDemandAmount}원\n'
        '[ 값 ] : {usePercent}% \n'
        '{extraMessage}```'
    )

    # 메시지와 레벨, 추가 메시지 정의
    if usePercent > 100:
        level = "CRITICAL"
        extraMessage = "예산 초과로 자동으로 서비스 중지됩니다."
        sendMessage = baseMessage.format(
            level=level,
            useAmount=useAmount,
            creditDiscount=creditDiscount,
            totalDemandAmount=totalDemandAmount,
            usePercent=usePercent,
            extraMessage=extraMessage
        )
        executeStopInstance()  # 서비스 중지 실행
    elif usePercent > 80:
        level = "CRITICAL"
        extraMessage = "예산이 얼마 남지 않았습니다. 예산이 초과되면 자동으로 서비스가 중지됩니다."
    elif usePercent > 60:
        level = "WARNING"
        extraMessage = "예산을 절약해야 합니다."
    elif usePercent > 40:
        level = "INFO"
        extraMessage = ""
    else:
        level = "INFO"
        extraMessage = ""

    # 메시지 작성
    sendMessage = baseMessage.format(
        level=level,
        useAmount=useAmount,
        creditDiscount=creditDiscount,
        totalDemandAmount=totalDemandAmount,
        usePercent=usePercent,
        extraMessage=extraMessage
    )

    try:
        response = client.chat_postMessage(
            channel=channelId,
            text=sendMessage
        )
        print(f"Message sent: {response['message']['text']}")
    except SlackApiError as e:
        print(f"Error sending message: {e.response['error']}")


def executeStopInstance():
    access_key, secret_key = ncp_credentials()
    region_code = "KR"
    server_api = "https://ncloud.apigw.ntruss.com"

    ncloud_api = NcloudApiClient(access_key, secret_key, server_api)
    uri = f"/vserver/v2/getServerInstanceList?serverInstanceStatusCode=RUN&responseFormatType=json" 
    response = ncloud_api.get_request(uri)
    response = response['getServerInstanceListResponse']['serverInstanceList']
    print(response)

    exclude_instance = []

    running_instance = []
    for instance in response:
        if instance['serverInstanceNo'] not in exclude_instance:
            running_instance.append(instance['serverInstanceNo'])

    print(running_instance)

    server_list = ""

    for i, instance in enumerate(running_instance, start=1):
        server_list += f"&serverInstanceNoList.{i}={instance}"

    uri = f"/vserver/v2/stopServerInstances?regionCode={region_code}{server_list}&responseFormatType=json"
    print(uri)

    response = ncloud_api.get_request(uri)

    print("인스턴스를 중지합니다.")
    
if __name__ == "__main__":
    main()
