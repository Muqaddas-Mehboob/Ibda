import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable, StudioInput as TextInput, StudioCard } from "../../../components/ui/StudioControls";
import { useState } from "react";
import { ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import {
  submitSupportRequest as saveSupportRequest,
  type SupportRequestReceipt,
} from "../services/support.service";
const LAST_UPDATED = "November 3, 2026";

type LegalSection = {
  title: string;
  paragraphs: string[];
};

function PageHeader({
  icon,
  title,
  description,
}: {
  icon: string;
  title: string;
  description: string;
}) {
  const router = useRouter();

  return (
    <>
      <Pressable
        onPress={() =>
          router.canGoBack() ? router.back() : router.replace("/settings")
        }
        accessibilityRole="button"
        accessibilityLabel="Go back"
        className="mb-4 h-11 w-11 items-center justify-center rounded-full border border-[#E2D9CF] bg-[#FAF8F4] active:bg-[#F4F0EA]"
      >
        <Text className="text-xl text-[#25221F]">‹</Text>
      </Pressable>
      <View className="mb-5 h-14 w-14 items-center justify-center rounded-2xl bg-[#F4F0EA]">
        <Text className="text-[14px] leading-[23px] tracking-[-0.3px] font-bold text-[#25221F]" variant="section">{icon}</Text>
      </View>
      <Text className="text-[22px] leading-[30px] tracking-[-0.3px] font-bold text-[#25221F]" variant="metric">{title}</Text>
      <Text className="mb-6 mt-3 text-[14px] leading-6 text-[#25221F]" variant="body">
        {description}
      </Text>
    </>
  );
}

function LegalDraftNotice() {
  return (
    <View className="mb-5 rounded-2xl border border-[#F4F0EA] bg-[#F4F0EA] p-4">
      <Text className="font-semibold text-[#25221F] text-[14px] leading-[22px]" variant="label">
        General draft - review before release
      </Text>
      <Text className="mt-1 text-[#25221F] text-[14px] leading-[22px]" variant="body">
        Ibda&apos;s legal publisher, contact details, and governing
        jurisdiction have not been provided. Have the responsible organization
        review and complete this document before relying on or publishing it.
      </Text>
    </View>
  );
}

function LegalPage({
  icon,
  title,
  description,
  sections,
}: {
  icon: string;
  title: string;
  description: string;
  sections: LegalSection[];
}) {
  return (
    <View className="flex-1 bg-[#FAF8F4]">
      <ScrollView
        contentContainerStyle={{
          padding: 24,
          paddingTop: 40,
          paddingBottom: 48, width: "100%", maxWidth: 960, alignSelf: "center",
        }}
        showsVerticalScrollIndicator={false}
      >
        <PageHeader icon={icon} title={title} description={description} />
        <Text className="mb-4 text-[14px] leading-[22px] text-[#25221F]" variant="body">
          Last updated: {LAST_UPDATED}
        </Text>
        <LegalDraftNotice />
        {sections.map((section) => (
          <StudioCard
            key={section.title}
            className="mb-4 rounded-3xl border border-[#25221F]/30 bg-[#F4F0EA] p-5"
          >
            <Text className="text-[14px] leading-[22px] font-bold text-[#25221F]" variant="cardTitle">
              {section.title}
            </Text>
            {section.paragraphs.map((paragraph, index) => (
              <Text
                key={`${section.title}-${index}`}
                className="mt-3 text-[#25221F] text-[14px] leading-[22px]" variant="body"
              >
                {paragraph}
              </Text>
            ))}
          </StudioCard>
        ))}
        <Text className="mt-1 text-[14px] leading-[23px] text-[#25221F]" variant="body">
          This general information is not legal advice. Contact the Ibda team
          through the Contact support page with questions.
        </Text>
      </ScrollView>
    </View>
  );
}

export function ContactSupportScreen() {
  const [replyEmail, setReplyEmail] = useState("");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [receipt, setReceipt] = useState<SupportRequestReceipt | null>(null);

  const sendSupportRequest = async () => {
    const trimmedSubject = subject.trim();
    const trimmedMessage = message.trim();
    if (!trimmedSubject || !trimmedMessage) {
      setSubmitError("Add a subject and describe how we can help.");
      return;
    }
    if (submitting) return;

    setSubmitting(true);
    setSubmitError("");
    setReceipt(null);
    try {
      const submitted = await saveSupportRequest({
        contact_email: replyEmail.trim(),
        subject: trimmedSubject,
        message: trimmedMessage,
      });
      setReceipt(submitted);
      setReplyEmail("");
      setSubject("");
      setMessage("");
    } catch (error) {
      setSubmitError(
        error instanceof Error
          ? error.message
          : "Could not send your support request. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <View className="flex-1 bg-[#FAF8F4]">
      <ScrollView
        contentContainerStyle={{
          padding: 24,
          paddingTop: 40,
          paddingBottom: 48, width: "100%", maxWidth: 960, alignSelf: "center",
        }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <PageHeader
          icon="?"
          title="Contact support"
          description="Send a message to the Ibda support team. Your request will be saved so the team can follow up."
        />
        {receipt ? (
          <View className="mb-5 rounded-2xl border border-[#E2D9CF] bg-[#F4F0EA] p-4">
            <Text className="font-semibold text-[#25221F] text-[14px] leading-[22px]" variant="label">
              Support request sent
            </Text>
            <Text className="mt-1 text-[#25221F] text-[14px] leading-[22px]" variant="body">
              Your request is saved. Reference: {receipt.id}
            </Text>
          </View>
        ) : null}
        {submitError ? (
          <View
            accessibilityRole="alert"
            className="mb-5 rounded-2xl border border-[#F4796B] bg-[#FAF8F4] p-4"
          >
            <Text className="text-[#25221F] text-[14px] leading-[22px]" variant="body">{submitError}</Text>
          </View>
        ) : null}
        {!replyEmail.trim() ? (
          <View className="mb-5 rounded-2xl border border-[#E2D9CF] bg-[#FAF8F4] p-4">
            <Text className="text-[#25221F] text-[14px] leading-[22px]" variant="body">
              Leave your email blank to use the email address on your Ibda
              account.
            </Text>
          </View>
        ) : null}
        <StudioCard className="rounded-3xl border border-[#E2D9CF] bg-[#F4F0EA] p-5">
          <Text className="mb-2 text-[14px] leading-[22px] font-semibold text-[#25221F]" variant="label">
            Contact email (optional)
          </Text>
          <TextInput
            value={replyEmail}
            onChangeText={setReplyEmail}
            placeholder="you@example.com"
            placeholderTextColor="#25221F"
            keyboardType="email-address"
            autoCapitalize="none"
            autoComplete="email"
            accessibilityLabel="Your email"
            className="min-h-12 rounded-[18px] border border-[#E2D9CF] bg-[#FAF8F4] px-4 text-[#25221F]"
          />
          <Text className="mb-2 mt-4 text-[14px] leading-[22px] font-semibold text-[#25221F]" variant="label">
            Subject
          </Text>
          <TextInput
            value={subject}
            onChangeText={setSubject}
            placeholder="How can we help?"
            placeholderTextColor="#25221F"
            maxLength={120}
            accessibilityLabel="Support request subject"
            className="min-h-12 rounded-[18px] border border-[#E2D9CF] bg-[#FAF8F4] px-4 text-[#25221F]"
          />
          <Text className="mb-2 mt-4 text-[14px] leading-[22px] font-semibold text-[#25221F]" variant="label">
            Message
          </Text>
          <TextInput
            value={message}
            onChangeText={setMessage}
            placeholder="Describe the issue or question..."
            placeholderTextColor="#25221F"
            multiline
            textAlignVertical="top"
            maxLength={4000}
            accessibilityLabel="Support request message"
            className="min-h-36 rounded-[18px] border border-[#E2D9CF] bg-[#FAF8F4] px-4 py-4 text-[#25221F]"
          />
          <Pressable
            onPress={() => void sendSupportRequest()}
            disabled={submitting}
            accessibilityRole="button"
            className={`mt-5 min-h-[48px] items-center justify-center rounded-[18px] px-4 ${
              submitting ? "bg-[#F4F0EA]" : "bg-[#C24A3C] active:bg-[#A63F32]"
            }`}
          >
            <Text className="font-bold text-[#FAF8F4] text-[14px] leading-[22px]" variant="button">
              {submitting ? "Sending..." : "Send support request"}
            </Text>
          </Pressable>
          <Text className="mt-3 text-[12px] leading-[23px] text-[#25221F]" variant="caption">
            Your message and contact email are saved with your
            support request so the Ibda team can respond.
          </Text>
        </StudioCard>
      </ScrollView>
    </View>
  );
}

export function PrivacyPolicyScreen() {
  return (
    <LegalPage
      icon="i"
      title="Privacy policy"
      description="What information Ibda uses, why it is needed, and the choices available to you."
      sections={[
        {
          title: "Information we use",
          paragraphs: [
            "When you create an account, Ibda processes your email address and account details managed through Supabase authentication. You may also provide a display name.",
            "To provide workspace features, Ibda stores the brand details, brand voice, drafts, generated posts, approvals, schedules, and notifications that you create or use.",
            "If you connect a social account, Ibda processes account identifiers and authorization tokens so you can manage supported publishing features. Social authorization tokens are stored encrypted by the backend.",
            "If you subscribe to a paid plan, Ibda processes subscription status and payment transaction references. Checkout and payment processing are provided through Stripe; Ibda does not ask you to enter card details into the app.",
          ],
        },
        {
          title: "How information is used",
          paragraphs: [
            "Ibda uses this information to authenticate you, operate your workspace, create and manage content, coordinate approvals and scheduled posts, show subscription information, respond to support requests, and protect the service.",
            "When you submit a support request, Ibda stores the subject, message, your account identifier, and contact email so the support team can review and respond. The contact email may be taken from your account when you leave the field blank.",
            "When you request AI content generation or optimization, the brand details and prompt information needed for that request are sent to the AI provider configured for Ibda. Review provider terms and avoid including confidential or sensitive information in prompts.",
            "Social networks receive information needed to connect accounts or perform actions you request. Their handling of that information is governed by their own privacy policies and your settings with them.",
          ],
        },
        {
          title: "Service providers and sharing",
          paragraphs: [
            "Ibda relies on service providers to run account authentication and app services, process payments, provide AI features, and connect to social networks. They receive information only as needed for those services or as otherwise required by law.",
            "Information may also be disclosed when required by law, to protect users and the service, or as part of a business transfer, subject to applicable law.",
          ],
        },
        {
          title: "Storage, security, and retention",
          paragraphs: [
            "Account information and workspace data are processed by Ibda's configured authentication and application services. Some session information is stored on your device so you can remain signed in.",
            "Ibda uses safeguards intended to protect information, including encrypted storage for social authorization tokens. No online service can guarantee absolute security.",
            "Information is kept while needed to operate your account and for legitimate operational, security, or legal purposes. You can start account deletion from Settings. Deletion may not remove content already shared with social networks, and some records may need to be retained where required by law.",
          ],
        },
        {
          title: "Your choices",
          paragraphs: [
            "You can update your display name, disconnect social accounts, sign out, or request account deletion from Settings. You can also manage permissions and remove content directly with the social networks where you published it.",
            "Support requests associated with your account are deleted when your account deletion completes.",
            "Depending on where you live, you may have rights to access, correct, delete, or restrict certain uses of your personal information. Contact support through this app to ask about a request.",
          ],
        },
        {
          title: "Children and policy updates",
          paragraphs: [
            "Ibda is a business productivity service and is not designed for children. The responsible organization should add the applicable minimum age and any required regional disclosures before release.",
            "This policy may be updated as Ibda changes. The latest version and its update date will be shown on this page.",
          ],
        },
      ]}
    />
  );
}

export function TermsOfServiceScreen() {
  return (
    <LegalPage
      icon="§"
      title="Terms of service"
      description="The basic rules for using Ibda's workspace, content, and connected services."
      sections={[
        {
          title: "Using Ibda",
          paragraphs: [
            "Ibda provides tools for managing brands, drafting social content, coordinating approvals, and scheduling or publishing content through supported integrations. Some features may depend on configuration or availability.",
            "You are responsible for keeping your account credentials secure, providing accurate account information, and activity performed through your account. Notify the Ibda team if you believe your account has been accessed without permission.",
          ],
        },
        {
          title: "Your content and permissions",
          paragraphs: [
            "You retain responsibility for content and materials you submit to Ibda. You confirm that you have the rights and permissions needed to use them and to authorize Ibda to process them to provide the features you request.",
            "You are responsible for reviewing generated or scheduled content before it is shared, ensuring it is accurate and lawful, and complying with applicable advertising, privacy, intellectual-property, and platform rules. AI-generated content may be inaccurate or unsuitable and should not be treated as professional advice.",
          ],
        },
        {
          title: "Connected services",
          paragraphs: [
            "Connecting a social account authorizes Ibda to use the permissions you grant for the features you request. You can disconnect an account in Settings. Social platforms may change their APIs, permissions, or rules, which can affect availability.",
            "Your use of third-party platforms and payment services is also subject to their own terms. Ibda is not responsible for third-party services it does not operate.",
          ],
        },
        {
          title: "Subscriptions and billing",
          paragraphs: [
            "Available plans, prices, billing periods, and applicable taxes are shown during checkout or in the app. Paid subscriptions are processed through the payment provider presented at checkout.",
            "You can review or cancel an eligible subscription from Plans & billing. Cancellation timing, access through the end of a paid period, and refunds are governed by the terms shown at purchase and applicable law.",
          ],
        },
        {
          title: "Acceptable use",
          paragraphs: [
            "Do not use Ibda to violate laws or third-party rights, send deceptive or abusive material, interfere with the service, attempt unauthorized access, or misuse connected accounts. Ibda may restrict activity that threatens users, platforms, or service integrity.",
          ],
        },
        {
          title: "Availability, termination, and changes",
          paragraphs: [
            "Ibda is provided as an evolving service. Features may be changed, interrupted, or discontinued. The responsible organization should define any service-level commitments and notice process before commercial release.",
            "You may stop using Ibda and request account deletion from Settings. Account deletion does not automatically remove information already held by connected third-party services.",
          ],
        },
        {
          title: "Disclaimers and governing terms",
          paragraphs: [
            "To the extent permitted by applicable law, Ibda is provided without a guarantee that it will be uninterrupted, error-free, or suitable for every purpose. Nothing in these draft terms limits rights that cannot legally be excluded.",
            "The legal publisher, governing law, dispute process, liability terms, and required regional consumer notices have not been supplied for this draft. These details must be completed and reviewed by the responsible organization before publication.",
          ],
        },
      ]}
    />
  );
}
